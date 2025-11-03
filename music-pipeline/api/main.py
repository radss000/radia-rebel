from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import List, Optional
import os
import tempfile
import requests
import numpy as np
import librosa
from pydantic import BaseModel, HttpUrl, validator

app = FastAPI(title="REBEL Music API", version="1.0.0")

# CORS pour React
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database config
DB_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', 'localhost'),
    'port': int(os.getenv('POSTGRES_PORT', 5432)),
    'database': os.getenv('POSTGRES_DB', 'rebel_music'),
    'user': os.getenv('POSTGRES_USER', 'rebel'),
    'password': os.getenv('POSTGRES_PASSWORD', 'rebel_password')
}

def get_db_connection():
    """Create database connection"""
    return psycopg2.connect(**DB_CONFIG)

class TrackIngestRequest(BaseModel):
    mongo_track_id: str
    title: str
    artist: str
    audio_url: HttpUrl
    genre: Optional[str] = None
    tags: Optional[List[str]] = None
    description: Optional[str] = None
    duration_seconds: Optional[int] = None

    @validator('tags', pre=True)
    def empty_list(cls, value):
        if value is None:
            return []
        return value

def normalise_feature(value: float, min_val: float, max_val: float) -> float:
    if value is None or np.isnan(value):
        return 0.5
    return float(np.clip((value - min_val) / (max_val - min_val + 1e-9), 0.0, 1.0))

def extract_audio_features(audio_path: str):
    try:
        y, sr = librosa.load(audio_path, sr=22050, mono=True)
        if not len(y):
            raise ValueError("Audio buffer empty")
        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        rms = librosa.feature.rms(y=y)[0]
        zcr = librosa.feature.zero_crossing_rate(y)[0]
        spectral_centroid = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
        spectral_bandwidth = librosa.feature.spectral_bandwidth(y=y, sr=sr)[0]
        rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr, roll_percent=0.85)[0]
        duration = librosa.get_duration(y=y, sr=sr)

        energy = normalise_feature(np.mean(rms) * 4, 0, 1.5)
        danceability = normalise_feature(np.mean(zcr) * 5, 0, 2.5)
        brightness = normalise_feature(np.mean(spectral_centroid), 500, 7000)
        bass = normalise_feature(1.0 / (np.mean(rolloff) + 1e-9), 0, 0.001)
        acousticness = normalise_feature(np.mean(spectral_bandwidth), 500, 4000)
        valence = normalise_feature(np.var(y), 0.01, 0.2)

        return {
            "tempo": float(np.clip(tempo, 40, 200)),
            "energy": energy,
            "danceability": danceability,
            "brightness": brightness,
            "bass": bass,
            "acousticness": acousticness,
            "valence": valence,
            "duration_sec": int(duration)
        }
    except Exception as exc:
        raise RuntimeError(f"Audio feature extraction failed: {exc}") from exc

def derive_position(features: dict):
    energy = features.get("energy", 0.5)
    dance = features.get("danceability", 0.5)
    brightness = features.get("brightness", 0.5)
    valence = features.get("valence", 0.5)

    x = (energy - 0.5) * 400
    y = (brightness - 0.5) * 400
    z = (dance - 0.5) * 400

    color = (
        float(np.clip(energy, 0, 1)),
        float(np.clip(brightness, 0, 1)),
        float(np.clip(valence, 0, 1))
    )

    size = 1.5 + energy * 1.5
    emissive = 0.2 + brightness * 0.8

    return (x, y, z), color, size, emissive

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
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                temp_file.write(chunk)
        temp_file.flush()
        temp_path = temp_file.name

        features = extract_audio_features(temp_path)

        if not payload.duration_seconds:
            payload.duration_seconds = features.get("duration_sec")

        position, color, size, emissive = derive_position(features)

        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

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
            "duration": payload.duration_seconds,
            "preview": str(payload.audio_url),
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
        conn.commit()
        cursor.close()
        conn.close()

        return {
            "success": True,
            "track_id": track_id,
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
