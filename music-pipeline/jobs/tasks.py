"""RQ task implementations for analysis jobs."""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import numpy as np
from psycopg2.extras import RealDictCursor, Json

from database.utils import get_db_connection
from processing.audio_features import extract_audio_features, derive_position, load_audio_mono
from processing.audio_assets.service import StorageClient, process_audio_asset

JOB_TASK_MAP = {
    "preview_fetch": "jobs.tasks.preview_fetch_task",
    "audio_features": "jobs.tasks.audio_features_task",
    "embedding": "jobs.tasks.embedding_task",
    "position": "jobs.tasks.position_task",
}

logger = logging.getLogger(__name__)

CLAP_AMODEL = os.getenv("CLAP_AMODEL", "HTSAT-base")
CLAP_ENABLE_FUSION = os.getenv("CLAP_ENABLE_FUSION", "false").lower() == "true"
CLAP_CHECKPOINT_PATH = os.getenv("CLAP_CHECKPOINT_PATH")
CLAP_MODEL_NAME = os.getenv("CLAP_MODEL_NAME", "clap-htsat-base")
CLAP_MODEL_VERSION = os.getenv("CLAP_MODEL_VERSION", "1.0")
EMBEDDING_SAMPLE_RATE = int(os.getenv("EMBEDDING_SAMPLE_RATE", 48000))
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "music_embeddings")
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")

_CLAP_MODEL = None
_QDRANT_CLIENT = None
_QDRANT_DISABLED = False


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


def _fetch_latest_asset_for_track(conn, track_id: int) -> Optional[Dict[str, Any]]:
    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """
            SELECT *
            FROM audio_assets
            WHERE track_id = %s
              AND deleted_at IS NULL
              AND fetch_status = 'fetched'
            ORDER BY fetched_at DESC NULLS LAST, created_at DESC
            LIMIT 1
            """,
            (track_id,),
        )
        return cursor.fetchone()


def _get_clap_model():
    global _CLAP_MODEL
    if _CLAP_MODEL is not None:
        return _CLAP_MODEL
    try:
        from laion_clap import CLAP_Module  # type: ignore
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("laion-clap not installed; pip install laion-clap to enable embeddings") from exc

    logger.info("Loading CLAP model (%s)...", CLAP_AMODEL)
    model = CLAP_Module(enable_fusion=CLAP_ENABLE_FUSION, amodel=CLAP_AMODEL)
    if CLAP_CHECKPOINT_PATH:
        model.load_ckpt(CLAP_CHECKPOINT_PATH)
    else:
        model.load_ckpt()
    _CLAP_MODEL = model
    logger.info("CLAP model ready")
    return _CLAP_MODEL


def _get_qdrant_client():
    global _QDRANT_CLIENT, _QDRANT_DISABLED
    if _QDRANT_DISABLED:
        return None
    if _QDRANT_CLIENT is not None:
        return _QDRANT_CLIENT
    try:
        from qdrant_client import QdrantClient  # type: ignore
        from qdrant_client.http import models as qmodels  # noqa: F401  # ensure dependency available
    except ImportError:  # pragma: no cover - optional dependency
        logger.warning("qdrant-client not installed; embeddings will stay local only")
        _QDRANT_DISABLED = True
        return None
    try:
        _QDRANT_CLIENT = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, api_key=QDRANT_API_KEY)
    except Exception as exc:  # pragma: no cover - optional path
        logger.warning("Could not connect to Qdrant (%s); skipping vector sync", exc)
        _QDRANT_DISABLED = True
        return None
    return _QDRANT_CLIENT


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
    conn = get_db_connection()
    try:
        job = _mark_job_running(conn, job_id)
        track_id = job.get("track_id")
        if not track_id:
            raise ValueError("Embedding job requires a track_id")
        asset = None
        asset_id = job.get("audio_asset_id")
        if asset_id:
            asset = _fetch_asset(conn, asset_id)
        if not asset:
            asset = _fetch_latest_asset_for_track(conn, track_id)
        if not asset:
            raise ValueError(f"No cached audio asset available for track {track_id}")
        storage_path = asset.get("storage_path")
        if not storage_path or not os.path.exists(storage_path):
            raise FileNotFoundError(f"Stored preview not found for asset {asset.get('id')}")

        audio, _ = load_audio_mono(storage_path, sample_rate=EMBEDDING_SAMPLE_RATE)
        if audio is None or not len(audio):
            raise ValueError("Audio buffer empty for embedding generation")

        clap_model = _get_clap_model()
        embedding = clap_model.get_audio_embedding_from_data(x=audio, use_tensor=False)[0]
        embedding = np.asarray(embedding, dtype=np.float32)

        embedding_id = str(uuid.uuid4())
        qdrant_id = embedding_id
        vector_dimensions = int(embedding.size)

        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO embeddings (id, track_id, model_name, model_version, vector_dimensions, qdrant_point_id)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (track_id) DO UPDATE
                    SET id = EXCLUDED.id,
                        model_name = EXCLUDED.model_name,
                        model_version = EXCLUDED.model_version,
                        vector_dimensions = EXCLUDED.vector_dimensions,
                        qdrant_point_id = EXCLUDED.qdrant_point_id
                """,
                (embedding_id, track_id, CLAP_MODEL_NAME, CLAP_MODEL_VERSION, vector_dimensions, qdrant_id),
            )
            cursor.execute(
                "UPDATE tracks SET embedding_id = %s WHERE id = %s",
                (embedding_id, track_id),
            )
        conn.commit()

        client = _get_qdrant_client()
        if client:
            try:
                from qdrant_client.http import models as qmodels  # type: ignore

                client.upsert(
                    collection_name=QDRANT_COLLECTION,
                    points=[
                        qmodels.PointStruct(
                            id=qdrant_id,
                            vector=embedding.tolist(),
                            payload={"track_id": track_id},
                        )
                    ],
                )
            except Exception as exc:  # pragma: no cover - optional path
                logger.warning("Failed to sync embedding %s to Qdrant: %s", embedding_id, exc)

        _mark_job_succeeded(
            conn,
            job_id,
            {
                "embedding_id": embedding_id,
                "vector_dimensions": vector_dimensions,
                "model": CLAP_MODEL_NAME,
                "qdrant_point_id": qdrant_id,
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
