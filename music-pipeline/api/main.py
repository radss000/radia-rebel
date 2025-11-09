from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from psycopg2.extras import RealDictCursor
from typing import Any, Dict, List, Optional, Literal
from datetime import datetime, timezone
from urllib.parse import urlparse
from uuid import UUID
import hashlib
import os
import tempfile
import json
import requests
from pydantic import BaseModel, HttpUrl, validator

from database.utils import get_db_connection, DB_CONFIG
from jobs.queue import enqueue_analysis_job, serialize_job
from processing.audio_features import extract_audio_features, derive_position

app = FastAPI(title="REBEL Music API", version="1.0.0")

# CORS pour React
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PROVIDER_TYPE_CHOICES = {"bandcamp", "discogs", "youtube_music", "spotify", "other"}
RIGHTS_SCOPE_CHOICES = {"restricted", "analysis_only", "public_preview"}


class TrackIngestRequest(BaseModel):
    mongo_track_id: str
    title: str
    artist: str
    audio_url: HttpUrl
    genre: Optional[str] = None
    tags: Optional[List[str]] = None
    description: Optional[str] = None
    duration_seconds: Optional[int] = None
    preview_provider_type: Optional[str] = None
    preview_provider_track_id: Optional[str] = None
    preview_source_url: Optional[HttpUrl] = None
    preview_rights_scope: Optional[str] = None
    preview_license_name: Optional[str] = None
    preview_license_url: Optional[HttpUrl] = None
    preview_license_notes: Optional[str] = None
    preview_expires_at: Optional[datetime] = None

    @validator('tags', pre=True)
    def empty_list(cls, value):
        if value is None:
            return []
        return value

    @validator('preview_provider_type')
    def normalise_provider_type(cls, value):
        if value is None:
            return value
        lower = value.lower()
        if lower not in PROVIDER_TYPE_CHOICES:
            raise ValueError(f"Unsupported provider type '{value}'")
        return lower

    @validator('preview_rights_scope')
    def normalise_rights_scope(cls, value):
        if value is None:
            return value
        lower = value.lower()
        if lower not in RIGHTS_SCOPE_CHOICES:
            raise ValueError(f"Unsupported rights scope '{value}'")
        return lower


class TrackSearchIngestRequest(BaseModel):
    artist: str
    title: str
    fallback_url: Optional[HttpUrl] = None
    requested_by: Optional[str] = None

    @validator("artist", "title")
    def ensure_text(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("Artist and title are required")
        return " ".join(value.strip().split())


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class JobEnqueueRequest(BaseModel):
    job_type: Literal["preview_fetch", "audio_features", "embedding", "position"]
    track_id: Optional[int] = None
    audio_asset_id: Optional[UUID] = None
    provider_type: Optional[str] = None
    provider_track_id: Optional[str] = None
    payload: Optional[dict] = None
    priority: int = 0
    requested_by: Optional[str] = None

    @validator('provider_type')
    def normalise_provider(cls, value):
        if value is None:
            return value
        lower = value.lower()
        if lower not in PROVIDER_TYPE_CHOICES:
            raise ValueError(f"Unsupported provider type '{value}'")
        return lower

    @validator('audio_asset_id', always=True)
    def ensure_asset(cls, value, values):
        job_type = values.get('job_type')
        if job_type in {"preview_fetch", "audio_features"} and value is None:
            raise ValueError("audio_asset_id is required for preview_fetch and audio_features jobs")
        return value

    @validator('track_id', always=True)
    def ensure_track(cls, value, values):
        job_type = values.get('job_type')
        if job_type in {"embedding", "position"} and value is None:
            raise ValueError("track_id is required for embedding and position jobs")
        return value


def infer_provider_type(url_value: Optional[str], explicit: Optional[str]) -> str:
    if explicit in PROVIDER_TYPE_CHOICES:
        return explicit
    if not url_value:
        return "other"
    hostname = urlparse(url_value).netloc.lower()
    if 'bandcamp' in hostname:
        return 'bandcamp'
    if 'discogs' in hostname:
        return 'discogs'
    if 'spotify' in hostname:
        return 'spotify'
    if 'youtube' in hostname or 'ytimg' in hostname:
        return 'youtube_music'
    return 'other'


def derive_provider_track_id(
    payload: TrackIngestRequest,
    fallback_source_url: str
) -> str:
    if payload.preview_provider_track_id:
        return payload.preview_provider_track_id
    if payload.mongo_track_id:
        return f"mongo-{payload.mongo_track_id}"
    # Use deterministic hash of source URL as last resort
    return hashlib.sha256(fallback_source_url.encode('utf-8')).hexdigest()


def _search_youtube_preview(artist: str, title: str) -> Dict[str, Any]:
    try:
        import yt_dlp  # type: ignore
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise HTTPException(
            status_code=500,
            detail="yt-dlp is required to search YouTube previews. Install it in the pipeline environment.",
        ) from exc

    query = f"ytsearch1:{artist} - {title} audio"
    ydl_opts = {
        "format": "bestaudio/best",
        "quiet": True,
        "skip_download": True,
        "no_warnings": True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:  # type: ignore[attr-defined]
            info = ydl.extract_info(query, download=False)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"YouTube search failed: {exc}") from exc

    entry: Optional[Dict[str, Any]] = None
    if isinstance(info, dict):
        if info.get("_type") == "video":
            entry = info
        else:
            entries = info.get("entries") or []
            if entries:
                entry = entries[0]

    if not entry:
        raise HTTPException(status_code=404, detail="No matching YouTube preview found")

    webpage_url = entry.get("webpage_url") or entry.get("url")
    if not webpage_url:
        raise HTTPException(status_code=500, detail="yt-dlp did not return a usable video URL")

    return {
        "id": entry.get("id"),
        "title": entry.get("title"),
        "duration": entry.get("duration"),
        "webpage_url": webpage_url,
        "thumbnail": entry.get("thumbnail"),
        "channel": entry.get("uploader") or entry.get("channel"),
        "description": entry.get("description"),
    }


def _ensure_track_and_asset(
    conn,
    *,
    artist: str,
    title: str,
    provider_type: str,
    provider_track_id: str,
    source_url: str,
    duration_seconds: Optional[int],
) -> Dict[str, Any]:
    """Create or update the track/audio_asset rows for the new preview."""
    youtube_value = source_url if provider_type == "youtube_music" else None
    normalized_provider = provider_type.lower()
    now = now_utc()

    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
        audio_asset_id: Optional[str] = None
        track_id: Optional[int] = None

        cursor.execute(
            """
            SELECT id, track_id
            FROM audio_assets
            WHERE provider_type = %s
              AND provider_track_id = %s
              AND deleted_at IS NULL
            LIMIT 1
            """,
            (normalized_provider, provider_track_id),
        )
        asset_row = cursor.fetchone()
        if asset_row:
            audio_asset_id = str(asset_row["id"])
            track_id = asset_row["track_id"]

        if not track_id:
            cursor.execute(
                """
                SELECT id
                FROM tracks
                WHERE lower(title) = lower(%s)
                  AND lower(artist) = lower(%s)
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (title, artist),
            )
            track_row = cursor.fetchone()
            if track_row:
                track_id = track_row["id"]

        if not track_id:
            cursor.execute(
                """
                INSERT INTO tracks (title, artist, preview_url, youtube_url, is_public)
                VALUES (%s, %s, %s, %s, TRUE)
                RETURNING id
                """,
                (title, artist, source_url, youtube_value),
            )
            track_id = cursor.fetchone()["id"]
        else:
            cursor.execute(
                """
                UPDATE tracks
                SET preview_url = %s,
                    youtube_url = CASE WHEN %s THEN %s ELSE youtube_url END,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (source_url, normalized_provider == "youtube_music", source_url, track_id),
            )

        asset_params = {
            "track_id": track_id,
            "provider_type": normalized_provider,
            "provider_track_id": provider_track_id,
            "source_url": source_url,
            "provider_preview_url": source_url,
            "duration_seconds": duration_seconds,
            "last_checked_at": now,
        }
        cursor.execute(
            """
            INSERT INTO audio_assets (
                track_id,
                provider_type,
                provider_track_id,
                source_url,
                provider_preview_url,
                storage_checksum,
                duration_seconds,
                rights_scope,
                license_name,
                license_url,
                license_notes,
                fetched_at,
                expires_at,
                last_checked_at,
                fetch_status,
                fetch_attempts
            ) VALUES (
                %(track_id)s,
                %(provider_type)s,
                %(provider_track_id)s,
                %(source_url)s,
                %(provider_preview_url)s,
                NULL,
                %(duration_seconds)s,
                'analysis_only',
                NULL,
                NULL,
                NULL,
                NULL,
                NULL,
                %(last_checked_at)s,
                'pending',
                0
            )
            ON CONFLICT (provider_type, provider_track_id)
            DO UPDATE SET
                track_id = EXCLUDED.track_id,
                source_url = EXCLUDED.source_url,
                provider_preview_url = EXCLUDED.provider_preview_url,
                rights_scope = EXCLUDED.rights_scope,
                duration_seconds = COALESCE(EXCLUDED.duration_seconds, audio_assets.duration_seconds),
                last_checked_at = EXCLUDED.last_checked_at,
                fetch_status = 'pending',
                fetch_attempts = 0,
                fetch_error = NULL,
                storage_path = NULL,
                storage_checksum = NULL,
                fetched_at = NULL,
                expires_at = EXCLUDED.expires_at,
                license_name = COALESCE(EXCLUDED.license_name, audio_assets.license_name),
                license_url = COALESCE(EXCLUDED.license_url, audio_assets.license_url),
                license_notes = COALESCE(EXCLUDED.license_notes, audio_assets.license_notes),
                provenance_version = audio_assets.provenance_version + 1,
                deleted_at = NULL
            RETURNING id;
            """,
            asset_params,
        )
        asset_row = cursor.fetchone()
        if asset_row:
            audio_asset_id = str(asset_row["id"])

    if not track_id or not audio_asset_id:
        raise HTTPException(status_code=500, detail="Failed to persist track/audio asset")

    return {"track_id": track_id, "audio_asset_id": audio_asset_id}

@app.get("/")
def root():
    """API root"""
    return {
        "name": "REBEL Music API",
        "version": "1.0.0",
        "endpoints": {
            "tracks": "/api/tracks",
            "sonic_map": "/api/tracks/sonic-map",
            "track_detail": "/api/tracks/{id}",
            "search": "/api/search"
        }
    }

@app.get("/api/tracks")
def get_tracks(
    limit: int = 1000,
    offset: int = 0,
    genre: Optional[str] = None
):
    """Get all tracks with optional filters"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        query = """
            SELECT 
                id, title, artist, album, genre, year, label,
                bpm, duration_sec,
                position_x, position_y, position_z,
                energy, danceability, acousticness, bass, brightness,
                color_r, color_g, color_b,
                sphere_size, emissive_intensity,
                preview_url, bandcamp_url, youtube_url, deezer_url, description_short,
                is_liked
            FROM tracks
            WHERE 1=1
        """
        params = []
        
        if genre:
            query += " AND genre ILIKE %s"
            params.append(f"%{genre}%")
        
        query += " ORDER BY created_at DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        
        cursor.execute(query, params)
        tracks = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return {
            "tracks": tracks,
            "count": len(tracks),
            "limit": limit,
            "offset": offset
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/tracks/ingest")
def ingest_track(payload: TrackIngestRequest):
    """Ingest a user uploaded track from the Node API into Postgres with real audio features"""
    temp_file = None
    try:
        response = requests.get(payload.audio_url, stream=True, timeout=30)
        if response.status_code != 200:
            raise HTTPException(status_code=502, detail=f"Failed to download audio (status {response.status_code})")

        temp_file = tempfile.NamedTemporaryFile(suffix=".tmp", delete=False)
        hasher = hashlib.sha256()
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                temp_file.write(chunk)
                hasher.update(chunk)
        temp_file.flush()
        temp_path = temp_file.name
        storage_checksum = hasher.hexdigest()

        features = extract_audio_features(temp_path)

        derived_duration = payload.duration_seconds or features.get("duration_sec")
        payload.duration_seconds = derived_duration

        position, color, size, emissive = derive_position(features)

        source_url = str(payload.preview_source_url or payload.audio_url)
        provider_preview_url = str(payload.audio_url)
        provider_type = infer_provider_type(source_url, payload.preview_provider_type)
        provider_track_id = derive_provider_track_id(payload, source_url)
        rights_scope = payload.preview_rights_scope or "analysis_only"
        last_checked_at = now_utc()
        expires_at = payload.preview_expires_at
        if expires_at and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        license_url = str(payload.preview_license_url) if payload.preview_license_url else None
        license_name = payload.preview_license_name
        license_notes = payload.preview_license_notes
        audio_asset_id = None

        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        try:
            cursor.execute("""
            INSERT INTO tracks (
                title,
                artist,
                genre,
                description_short,
                duration_sec,
                preview_url,
                tags,
                bpm,
                energy,
                danceability,
                acousticness,
                brightness,
                bass,
                valence,
                position_x,
                position_y,
                position_z,
                color_r,
                color_g,
                color_b,
                sphere_size,
                emissive_intensity,
                is_public
            ) VALUES (
                %(title)s,
                %(artist)s,
                %(genre)s,
                %(description)s,
                %(duration)s,
                %(preview)s,
                %(tags)s,
                %(tempo)s,
                %(energy)s,
                %(danceability)s,
                %(acousticness)s,
                %(brightness)s,
                %(bass)s,
                %(valence)s,
                %(pos_x)s,
                %(pos_y)s,
                %(pos_z)s,
                %(color_r)s,
                %(color_g)s,
                %(color_b)s,
                %(sphere_size)s,
                %(emissive)s,
                TRUE
            )
            RETURNING id;
            """, {
                "title": payload.title,
                "artist": payload.artist,
                "genre": payload.genre,
                "description": payload.description,
                "duration": derived_duration,
                "preview": provider_preview_url,
                "tags": payload.tags if payload.tags else None,
                "tempo": features["tempo"],
                "energy": features["energy"],
                "danceability": features["danceability"],
                "acousticness": features["acousticness"],
                "brightness": features["brightness"],
                "bass": features["bass"],
                "valence": features["valence"],
                "pos_x": position[0],
                "pos_y": position[1],
                "pos_z": position[2],
                "color_r": color[0],
                "color_g": color[1],
                "color_b": color[2],
                "sphere_size": size,
                "emissive": emissive
            })

            track_id = cursor.fetchone()["id"]

            asset_params = {
                "track_id": track_id,
                "provider_type": provider_type,
                "provider_track_id": provider_track_id,
                "source_url": source_url,
                "provider_preview_url": provider_preview_url,
                "storage_checksum": storage_checksum,
                "duration_seconds": derived_duration,
                "rights_scope": rights_scope,
                "license_name": license_name,
                "license_url": license_url,
                "license_notes": license_notes,
                "fetched_at": None,
                "expires_at": expires_at,
                "last_checked_at": last_checked_at,
                "fetch_status": "pending",
                "fetch_attempts": 0
            }

            cursor.execute("""
                INSERT INTO audio_assets (
                    track_id,
                    provider_type,
                    provider_track_id,
                    source_url,
                    provider_preview_url,
                    storage_checksum,
                    duration_seconds,
                    rights_scope,
                    license_name,
                    license_url,
                    license_notes,
                    fetched_at,
                    expires_at,
                    last_checked_at,
                    fetch_status,
                    fetch_attempts
                ) VALUES (
                    %(track_id)s,
                    %(provider_type)s,
                    %(provider_track_id)s,
                    %(source_url)s,
                    %(provider_preview_url)s,
                    %(storage_checksum)s,
                    %(duration_seconds)s,
                    %(rights_scope)s,
                    %(license_name)s,
                    %(license_url)s,
                    %(license_notes)s,
                    %(fetched_at)s,
                    %(expires_at)s,
                    %(last_checked_at)s,
                    %(fetch_status)s,
                    %(fetch_attempts)s
                )
                ON CONFLICT (provider_type, provider_track_id)
                DO UPDATE SET
                    track_id = EXCLUDED.track_id,
                    source_url = EXCLUDED.source_url,
                    provider_preview_url = EXCLUDED.provider_preview_url,
                    rights_scope = EXCLUDED.rights_scope,
                    license_name = EXCLUDED.license_name,
                    license_url = EXCLUDED.license_url,
                    license_notes = EXCLUDED.license_notes,
                    fetched_at = NULL,
                    expires_at = EXCLUDED.expires_at,
                    last_checked_at = EXCLUDED.last_checked_at,
                    fetch_status = 'pending',
                    fetch_attempts = 0,
                    storage_checksum = EXCLUDED.storage_checksum,
                    duration_seconds = COALESCE(EXCLUDED.duration_seconds, audio_assets.duration_seconds),
                    fetch_error = NULL,
                    provenance_version = audio_assets.provenance_version + 1,
                    deleted_at = NULL
                RETURNING id;
            """, asset_params)
            asset_row = cursor.fetchone()
            if asset_row and asset_row.get("id"):
                audio_asset_id = str(asset_row["id"])

            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()

        return {
            "success": True,
            "track_id": track_id,
            "audio_asset_id": audio_asset_id,
            "features": features,
            "position": {
                "x": position[0],
                "y": position[1],
                "z": position[2]
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if temp_file is not None:
            try:
                temp_file.close()
                os.unlink(temp_file.name)
            except Exception:
                pass


@app.post("/api/tracks/search-ingest")
def search_and_ingest_track(payload: TrackSearchIngestRequest):
    """Search YouTube (or use a manual URL) then enqueue the full analysis pipeline."""
    artist = payload.artist.strip()
    title = payload.title.strip()
    requested_by = payload.requested_by or "search-ingest"

    if payload.fallback_url:
        source_url = str(payload.fallback_url)
        provider_type = infer_provider_type(source_url, None)
        provider_track_id = hashlib.sha256(source_url.encode("utf-8")).hexdigest()
        selected_preview = {
            "id": provider_track_id,
            "title": title,
            "webpage_url": source_url,
            "channel": artist,
            "duration": None,
            "is_manual": True,
        }
    else:
        selected_preview = _search_youtube_preview(artist, title)
        source_url = selected_preview["webpage_url"]
        provider_type = "youtube_music"
        provider_track_id = selected_preview.get("id") or hashlib.sha256(source_url.encode("utf-8")).hexdigest()
        selected_preview["is_manual"] = False

    duration_seconds = selected_preview.get("duration")
    if isinstance(duration_seconds, float):
        duration_seconds = int(duration_seconds)
    elif isinstance(duration_seconds, str) and duration_seconds.isdigit():
        duration_seconds = int(duration_seconds)
    elif duration_seconds is not None and not isinstance(duration_seconds, int):
        try:
            duration_seconds = int(duration_seconds)
        except Exception:
            duration_seconds = None

    selected_preview["provider_type"] = provider_type
    selected_preview["search_query"] = f"{artist} - {title}"
    selected_preview["duration_seconds"] = duration_seconds

    conn = get_db_connection()
    try:
        upsert_result = _ensure_track_and_asset(
            conn,
            artist=artist,
            title=title,
            provider_type=provider_type,
            provider_track_id=provider_track_id,
            source_url=source_url,
            duration_seconds=duration_seconds,
        )
        conn.commit()
    except HTTPException:
        conn.rollback()
        raise
    except Exception as exc:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        conn.close()

    jobs = []
    try:
        context_asset_id = UUID(upsert_result["audio_asset_id"])
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Invalid audio asset id: {exc}") from exc

    for job_type in ("preview_fetch", "audio_features", "embedding", "position"):
        payload_kwargs = {
            "job_type": job_type,
            "requested_by": requested_by,
        }
        if job_type in {"preview_fetch", "audio_features"}:
            payload_kwargs["audio_asset_id"] = context_asset_id
            payload_kwargs["provider_type"] = provider_type
            payload_kwargs["provider_track_id"] = provider_track_id
        if job_type in {"audio_features", "embedding", "position"}:
            payload_kwargs["track_id"] = upsert_result["track_id"]
        job_request = JobEnqueueRequest(**payload_kwargs)
        enqueue_result = enqueue_job(job_request)
        jobs.append(
            {
                "type": job_type,
                "job": enqueue_result["job"],
                "queue_job_id": enqueue_result["queue_job_id"],
            }
        )

    return {
        "track_id": upsert_result["track_id"],
        "audio_asset_id": upsert_result["audio_asset_id"],
        "provider_type": provider_type,
        "provider_track_id": provider_track_id,
        "preview_source_url": source_url,
        "selected_preview": selected_preview,
        "jobs": jobs,
    }


@app.post("/api/jobs/enqueue")
def enqueue_job(payload: JobEnqueueRequest):
    try:
        job_row, queue_job_id = enqueue_analysis_job(
            job_type=payload.job_type,
            track_id=payload.track_id,
            audio_asset_id=str(payload.audio_asset_id) if payload.audio_asset_id else None,
            provider_type=payload.provider_type,
            provider_track_id=payload.provider_track_id,
            payload=payload.payload,
            priority=payload.priority,
            requested_by=payload.requested_by,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {"job": serialize_job(job_row), "queue_job_id": queue_job_id}


@app.get("/api/jobs/{job_id}")
def get_job_status(job_id: UUID):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT * FROM analysis_jobs WHERE id = %s", (str(job_id),))
    job = cursor.fetchone()
    cursor.close()
    conn.close()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return serialize_job(job)

@app.get("/api/tracks/sonic-map")
def get_sonic_map_data(limit: int = 1000):
    """Get tracks formatted for Sonic Map visualization"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute("""
            SELECT 
                id::text as id,
                title,
                artist,
                genre,
                year,
                COALESCE(is_liked, false) as liked,
                json_build_object(
                    'x', position_x,
                    'y', position_y,
                    'z', position_z
                ) as position,
                json_build_object(
                    'r', color_r,
                    'g', color_g,
                    'b', color_b
                ) as color,
                sphere_size as size,
                emissive_intensity as "emissiveIntensity",
                json_build_object(
                    'tempo', bpm,
                    'energy', energy,
                    'danceability', danceability,
                    'acousticness', acousticness,
                    'brightness', brightness,
                    'bass', bass
                ) as audio,
                json_build_object(
                    'duration_ms', duration_sec * 1000
                ) as "originalFormat",
                preview_url,
                json_build_object(
                    'bandcamp', bandcamp_url,
                    'youtube', youtube_url,
                    'deezer', deezer_url,
                    'discogs', CASE 
                        WHEN discogs_id IS NOT NULL THEN CONCAT('https://www.discogs.com/release/', discogs_id::text)
                        ELSE NULL
                    END
                ) as links
            FROM tracks
            WHERE position_x IS NOT NULL
            LIMIT %s
        """, (limit,))
        
        tracks = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return tracks
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/tracks/{track_id}")
def get_track_detail(track_id: int):
    """Get detailed information for a single track"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute("""
            SELECT 
                t.*,
                COALESCE(
                    json_agg(
                        json_build_object(
                            'platform', tl.platform,
                            'url', tl.url,
                            'type', tl.link_type
                        )
                    ) FILTER (WHERE tl.id IS NOT NULL),
                    '[]'
                ) as links
            FROM tracks t
            LEFT JOIN track_links tl ON t.id = tl.track_id AND tl.is_active = TRUE
            WHERE t.id = %s
            GROUP BY t.id
        """, (track_id,))
        
        track = cursor.fetchone()
        
        if not track:
            raise HTTPException(status_code=404, detail="Track not found")
        
        cursor.close()
        conn.close()
        
        return track
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/search")
def search_tracks(q: str, limit: int = 20):
    """Full-text search for tracks"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute("""
            SELECT 
                id, title, artist, album, genre, year,
                ts_rank(
                    to_tsvector('english', 
                        coalesce(title, '') || ' ' || 
                        coalesce(artist, '') || ' ' || 
                        coalesce(album, '')
                    ),
                    plainto_tsquery('english', %s)
                ) as rank
            FROM tracks
            WHERE to_tsvector('english', 
                    coalesce(title, '') || ' ' || 
                    coalesce(artist, '') || ' ' || 
                    coalesce(album, '')
                ) @@ plainto_tsquery('english', %s)
            ORDER BY rank DESC
            LIMIT %s
        """, (q, q, limit))
        
        results = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return {
            "query": q,
            "results": results,
            "count": len(results)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/genres")
def get_genres():
    """Get list of all genres"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT DISTINCT genre, COUNT(*) as count
            FROM tracks
            WHERE genre IS NOT NULL
            GROUP BY genre
            ORDER BY count DESC
        """)
        
        genres = [{"name": row[0], "count": row[1]} for row in cursor.fetchall()]
        
        cursor.close()
        conn.close()
        
        return {"genres": genres}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/stats")
def get_stats():
    """Get database statistics"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute("""
            SELECT 
                COUNT(*) as total_tracks,
                COUNT(DISTINCT artist) as total_artists,
                COUNT(DISTINCT genre) as total_genres,
                COUNT(*) FILTER (WHERE position_x IS NOT NULL) as tracks_with_positions
            FROM tracks
        """)
        
        stats = cursor.fetchone()
        
        cursor.close()
        conn.close()
        
        return stats
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting REBEL Music API...")
    print("📍 API: http://localhost:8000")
    print("📖 Docs: http://localhost:8000/docs")
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)  # ⬅️ Change ici
