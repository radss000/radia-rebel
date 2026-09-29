"""UMAP-based track positioning job."""

from __future__ import annotations

import logging
import os
import time
import json
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
from dotenv import load_dotenv

from database.utils import get_db_connection
from processing.positioning import UMAPPositioner

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PIPELINE_ROOT = Path(__file__).resolve().parents[1]
pipeline_env = PIPELINE_ROOT / ".env"
repo_env = PROJECT_ROOT / ".env"
if pipeline_env.exists():
    load_dotenv(dotenv_path=pipeline_env, override=False)
if repo_env.exists():
    load_dotenv(dotenv_path=repo_env, override=False)
if not pipeline_env.exists() and not repo_env.exists():
    load_dotenv(override=False)

QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "music_embeddings")
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
WS_EVENTS_CHANNEL = os.getenv("WS_EVENTS_CHANNEL", "ws_events")

UMAP_RECALC_INTERVAL = int(os.getenv("UMAP_RECALC_INTERVAL", 10))
UMAP_MAX_TRACKS = int(os.getenv("UMAP_MAX_TRACKS", 5000))

_QDRANT_CLIENT = None
_QDRANT_DISABLED = False
_REDIS_CLIENT = None


def run_position_job(track_id: str):
    positioner = UMAPPositioner()
    track_id_int = int(track_id)

    new_emb = get_track_embedding(track_id_int)
    if new_emb is None:
        logger.error("No embedding for track %s", track_id)
        return None

    all_embs, all_ids = get_all_embeddings(limit=UMAP_MAX_TRACKS)
    if not len(all_ids):
        logger.error("No embeddings available for UMAP positioning")
        return None

    pending_count = get_unpositioned_count()

    if pending_count >= UMAP_RECALC_INTERVAL or len(all_ids) < 15:
        t0 = time.time()
        positions = positioner.fit_transform(all_embs)
        dt = int((time.time() - t0) * 1000)
        for i, tid in enumerate(all_ids):
            update_track_position(tid, *positions[i], method="umap_full")
        reset_unpositioned_count()
        logger.info("UMAP full recalc: %s tracks in %sms", len(all_ids), dt)
        if track_id_int not in all_ids:
            logger.error("Track %s missing from embedding set", track_id)
            return None
        x, y, z = positions[all_ids.index(track_id_int)]
    else:
        existing_pos = get_all_positions(all_ids)
        xyz = positioner.nearest_neighbor_position(new_emb, all_embs, existing_pos)
        x, y, z = map(float, xyz)
        update_track_position(track_id_int, x, y, z, method="umap_approx")
        logger.info("UMAP approx: nearest-neighbor (%s/%s)", pending_count, UMAP_RECALC_INTERVAL)

    publish_ws_event("track_positioned", {"track_id": track_id_int, "x": float(x), "y": float(y), "z": float(z)})
    return {"x": float(x), "y": float(y), "z": float(z)}


def get_track_embedding(track_id: int) -> Optional[np.ndarray]:
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT qdrant_point_id
                FROM embeddings
                WHERE track_id = %s
                LIMIT 1
                """,
                (track_id,),
            )
            row = cursor.fetchone()
        if not row or not row[0]:
            return None
        point_id = row[0]
    finally:
        conn.close()

    client = _get_qdrant_client()
    if not client:
        return None

    points = client.retrieve(collection_name=QDRANT_COLLECTION, ids=[point_id], with_vectors=True)
    if not points:
        return None
    return np.asarray(points[0].vector, dtype=np.float32)


def get_all_embeddings(limit: int = UMAP_MAX_TRACKS) -> Tuple[np.ndarray, List[int]]:
    client = _get_qdrant_client()
    if not client:
        return np.empty((0, 0), dtype=np.float32), []

    points, _ = client.scroll(
        collection_name=QDRANT_COLLECTION,
        limit=limit,
        with_payload=True,
        with_vectors=True,
    )
    if not points:
        return np.empty((0, 0), dtype=np.float32), []

    embeddings = np.array([p.vector for p in points], dtype=np.float32)
    ids = [int(p.payload.get("track_id")) for p in points]
    return embeddings, ids


def get_all_positions(track_ids: List[int]) -> np.ndarray:
    if not track_ids:
        return np.empty((0, 3), dtype=np.float32)
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, position_x, position_y, position_z
                FROM tracks
                WHERE id = ANY(%s)
                """,
                (track_ids,),
            )
            rows = cursor.fetchall()
    finally:
        conn.close()

    positions_by_id = {row[0]: row[1:4] for row in rows}
    ordered_positions = []
    for track_id in track_ids:
        pos = positions_by_id.get(track_id)
        if pos is None:
            ordered_positions.append((0.0, 0.0, 0.0))
        else:
            ordered_positions.append((pos[0] or 0.0, pos[1] or 0.0, pos[2] or 0.0))
    return np.asarray(ordered_positions, dtype=np.float32)


def update_track_position(track_id: int, x: float, y: float, z: float, method: str) -> None:
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE tracks
                SET position_x = %s,
                    position_y = %s,
                    position_z = %s,
                    position_method = %s,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (float(x), float(y), float(z), method, track_id),
            )
        conn.commit()
    finally:
        conn.close()


def get_unpositioned_count() -> int:
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT(*)
                FROM tracks
                WHERE position_method IS NULL
                   OR position_method = 'pending'
                   OR position_x IS NULL
                   OR position_y IS NULL
                   OR position_z IS NULL
                """
            )
            count = cursor.fetchone()[0]
    finally:
        conn.close()
    return int(count)


def reset_unpositioned_count() -> None:
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE tracks
                SET position_method = 'umap_full'
                WHERE position_method IS NULL
                   OR position_method = 'pending'
                """
            )
        conn.commit()
    finally:
        conn.close()


def publish_ws_event(event: str, payload: dict) -> None:
    client = _get_redis_client()
    message = json.dumps({"event": event, "payload": payload})
    if not client:
        logger.info("WS event dropped (no Redis): %s", message)
        return
    try:
        client.publish(WS_EVENTS_CHANNEL, message)
        logger.info("WS event published: %s", message)
    except Exception as exc:
        logger.warning("Failed to publish WS event (%s): %s", event, exc)


def _get_qdrant_client():
    global _QDRANT_CLIENT, _QDRANT_DISABLED
    if _QDRANT_DISABLED:
        return None
    if _QDRANT_CLIENT is not None:
        return _QDRANT_CLIENT
    try:
        from qdrant_client import QdrantClient  # type: ignore
        from qdrant_client.http import models as qmodels  # noqa: F401
    except ImportError:
        logger.warning("qdrant-client not installed; cannot fetch embeddings")
        _QDRANT_DISABLED = True
        return None
    try:
        _QDRANT_CLIENT = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, api_key=QDRANT_API_KEY)
    except Exception as exc:
        logger.warning("Could not connect to Qdrant (%s); cannot fetch embeddings", exc)
        _QDRANT_DISABLED = True
        return None
    return _QDRANT_CLIENT


def _get_redis_client():
    global _REDIS_CLIENT
    if _REDIS_CLIENT is not None:
        return _REDIS_CLIENT
    try:
        from redis import Redis  # type: ignore
    except ImportError:
        logger.warning("redis not installed; cannot publish WS events")
        return None
    try:
        _REDIS_CLIENT = Redis.from_url(REDIS_URL)
    except Exception as exc:
        logger.warning("Could not connect to Redis (%s); cannot publish WS events", exc)
        _REDIS_CLIENT = None
    return _REDIS_CLIENT
