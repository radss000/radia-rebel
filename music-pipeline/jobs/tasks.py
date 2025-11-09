"""RQ task implementations for analysis jobs."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import numpy as np
from psycopg2.extras import RealDictCursor, Json

from database.utils import get_db_connection
from processing.audio_features import extract_audio_features, derive_position
from processing.audio_assets.service import StorageClient, process_audio_asset

JOB_TASK_MAP = {
    "preview_fetch": "jobs.tasks.preview_fetch_task",
    "audio_features": "jobs.tasks.audio_features_task",
    "embedding": "jobs.tasks.embedding_task",
    "position": "jobs.tasks.position_task",
}


def _mark_job_running(conn, job_id: str) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """
            UPDATE analysis_jobs
            SET status = 'running',
                attempts = attempts + 1,
                last_attempt_at = %s,
                started_at = COALESCE(started_at, %s)
            WHERE id = %s
            RETURNING *
            """,
            (now, now, job_id),
        )
        job = cursor.fetchone()
        if not job:
            raise ValueError(f"Job {job_id} not found")
    conn.commit()
    return job


def _mark_job_succeeded(conn, job_id: str, result_metadata: Optional[Dict[str, Any]] = None) -> None:
    now = datetime.now(timezone.utc)
    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
        if result_metadata is not None:
            cursor.execute(
                """
                UPDATE analysis_jobs
                SET status = 'succeeded',
                    completed_at = %s,
                    updated_at = %s,
                    result_metadata = COALESCE(result_metadata, '{}'::jsonb) || %s
                WHERE id = %s
                """,
                (now, now, Json(result_metadata), job_id),
            )
        else:
            cursor.execute(
                """
                UPDATE analysis_jobs
                SET status = 'succeeded',
                    completed_at = %s,
                    updated_at = %s
                WHERE id = %s
                """,
                (now, now, job_id),
            )
    conn.commit()


def _mark_job_failed(conn, job_id: str, message: str) -> None:
    now = datetime.now(timezone.utc)
    with conn.cursor() as cursor:
        cursor.execute(
            """
            UPDATE analysis_jobs
            SET status = 'failed',
                error_message = %s,
                updated_at = %s,
                completed_at = %s
            WHERE id = %s
            """,
            (message[:500], now, now, job_id),
        )
    conn.commit()


def _fetch_asset(conn, asset_id: str) -> Optional[Dict[str, Any]]:
    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute("SELECT * FROM audio_assets WHERE id = %s", (asset_id,))
        return cursor.fetchone()


def _fetch_track(conn, track_id: int) -> Optional[Dict[str, Any]]:
    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """
            SELECT id, title, artist, energy, danceability, acousticness,
                   bass, brightness, valence, bpm, duration_sec,
                   color_r, color_g, color_b, sphere_size, emissive_intensity
            FROM tracks
            WHERE id = %s
            """,
            (track_id,),
        )
        return cursor.fetchone()


def preview_fetch_task(job_id: str) -> None:
    conn = get_db_connection()
    storage = StorageClient()
    try:
        job = _mark_job_running(conn, job_id)
        asset_id = job.get("audio_asset_id")
        if not asset_id:
            raise ValueError("Job missing audio_asset_id")
        result = process_audio_asset(conn, str(asset_id), storage=storage, commit=True)
        _mark_job_succeeded(conn, job_id, {"storage_path": result["storage_path"], "checksum": result["checksum"]})
    except Exception as exc:  # pragma: no cover - resilience
        _mark_job_failed(conn, job_id, str(exc))
        raise
    finally:
        conn.close()


def audio_features_task(job_id: str) -> None:
    conn = get_db_connection()
    try:
        job = _mark_job_running(conn, job_id)
        asset_id = job.get("audio_asset_id")
        if not asset_id:
            raise ValueError("Job missing audio_asset_id")
        asset = _fetch_asset(conn, asset_id)
        if not asset:
            raise ValueError(f"Audio asset {asset_id} not found")
        storage_path = asset.get("storage_path")
        if not storage_path or not os.path.exists(storage_path):
            raise FileNotFoundError(f"Stored preview not found for asset {asset_id}")
        features = extract_audio_features(storage_path)
        track_id = job.get("track_id") or asset.get("track_id")
        if not track_id:
            raise ValueError("No track associated with job")
        duration = features.get("duration_sec")
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE tracks
                SET bpm = %s,
                    energy = %s,
                    danceability = %s,
                    acousticness = %s,
                    brightness = %s,
                    bass = %s,
                    valence = %s,
                    duration_sec = COALESCE(duration_sec, %s),
                    updated_at = NOW()
                WHERE id = %s
                """,
                (
                    features["tempo"],
                    features["energy"],
                    features["danceability"],
                    features["acousticness"],
                    features["brightness"],
                    features["bass"],
                    features["valence"],
                    duration,
                    track_id,
                ),
            )
            cursor.execute(
                """
                UPDATE audio_assets
                SET duration_seconds = %s,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (duration, asset_id),
            )
        conn.commit()
        _mark_job_succeeded(conn, job_id, {"features": features})
    except Exception as exc:  # pragma: no cover
        conn.rollback()
        _mark_job_failed(conn, job_id, str(exc))
        raise
    finally:
        conn.close()


def embedding_task(job_id: str) -> None:
    """Generate a placeholder embedding vector based on track features."""
    conn = get_db_connection()
    try:
        job = _mark_job_running(conn, job_id)
        track_id = job.get("track_id")
        if not track_id:
            raise ValueError("Embedding job requires a track_id")
        track = _fetch_track(conn, track_id)
        if not track:
            raise ValueError(f"Track {track_id} not found")

        feature_vector = np.array(
            [
                track.get("energy") or 0.5,
                track.get("danceability") or 0.5,
                track.get("acousticness") or 0.5,
                track.get("bass") or 0.5,
                track.get("brightness") or 0.5,
                track.get("valence") or 0.5,
                (track.get("bpm") or 120) / 200.0,
            ],
            dtype=float,
        )
        base_vector = np.tile(feature_vector, int(np.ceil(128 / feature_vector.size)))[:128]
        norm = np.linalg.norm(base_vector)
        if norm > 0:
            base_vector = base_vector / norm
        embedding_id = str(uuid.uuid4())
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO embeddings (id, track_id, model_name, model_version, vector_dimensions)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (track_id) DO UPDATE
                    SET id = EXCLUDED.id,
                        model_name = EXCLUDED.model_name,
                        model_version = EXCLUDED.model_version,
                        vector_dimensions = EXCLUDED.vector_dimensions
                """,
                (embedding_id, track_id, "placeholder-feature-vector", "0.1", base_vector.size),
            )
            cursor.execute(
                "UPDATE tracks SET embedding_id = %s WHERE id = %s",
                (embedding_id, track_id),
            )
        conn.commit()
        _mark_job_succeeded(
            conn,
            job_id,
            {
                "embedding_id": embedding_id,
                "vector_dimensions": int(base_vector.size),
                "note": "placeholder embedding generated from track features",
            },
        )
    except Exception as exc:  # pragma: no cover
        conn.rollback()
        _mark_job_failed(conn, job_id, str(exc))
        raise
    finally:
        conn.close()


def position_task(job_id: str) -> None:
    conn = get_db_connection()
    try:
        job = _mark_job_running(conn, job_id)
        track_id = job.get("track_id")
        if not track_id:
            raise ValueError("Position job requires a track_id")
        track = _fetch_track(conn, track_id)
        if not track:
            raise ValueError(f"Track {track_id} not found")

        features = {
            "energy": track.get("energy", 0.5),
            "danceability": track.get("danceability", 0.5),
            "acousticness": track.get("acousticness", 0.5),
            "brightness": track.get("brightness", 0.5),
            "bass": track.get("bass", 0.5),
            "valence": track.get("valence", 0.5),
        }
        position, color, size, emissive = derive_position(features)
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE tracks
                SET position_x = %s,
                    position_y = %s,
                    position_z = %s,
                    color_r = %s,
                    color_g = %s,
                    color_b = %s,
                    sphere_size = %s,
                    emissive_intensity = %s,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (
                    float(position[0]),
                    float(position[1]),
                    float(position[2]),
                    float(color[0]),
                    float(color[1]),
                    float(color[2]),
                    float(size),
                    float(emissive),
                    track_id,
                ),
            )
        conn.commit()
        _mark_job_succeeded(
            conn,
            job_id,
            {
                "position": {"x": float(position[0]), "y": float(position[1]), "z": float(position[2])},
                "color": {"r": float(color[0]), "g": float(color[1]), "b": float(color[2])},
                "sphere_size": float(size),
            },
        )
    except Exception as exc:  # pragma: no cover
        conn.rollback()
        _mark_job_failed(conn, job_id, str(exc))
        raise
    finally:
        conn.close()
