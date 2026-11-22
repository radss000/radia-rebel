"""Versioned and quality-gated Sonic Map positioning job."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from dotenv import load_dotenv
from psycopg2.extras import Json, execute_values

from database.utils import get_db_connection
from processing.positioning import UMAPPositioner, umap_params_for_count

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
UMAP_KNN_K = int(os.getenv("UMAP_KNN_K", 5))
UMAP_KNN_MIN_NEIGHBORS = int(os.getenv("UMAP_KNN_MIN_NEIGHBORS", 3))
UMAP_KNN_MIN_SIMILARITY = float(os.getenv("UMAP_KNN_MIN_SIMILARITY", 0.01))
UMAP_QUALITY_K = int(os.getenv("UMAP_QUALITY_K", 10))
UMAP_MIN_TRUSTWORTHINESS = float(os.getenv("UMAP_MIN_TRUSTWORTHINESS", 0.90))
UMAP_MIN_NEIGHBOR_RECALL = float(os.getenv("UMAP_MIN_NEIGHBOR_RECALL", 0.35))

FULL_POSITION_METHODS = ("clap_umap_full", "umap_full")
VALID_CLAP_POSITION_METHODS = FULL_POSITION_METHODS + ("clap_knn_approx", "umap_approx")

_QDRANT_CLIENT = None
_QDRANT_DISABLED = False
_REDIS_CLIENT = None
_POSITIONING_SCHEMA_READY = False


@dataclass(frozen=True)
class TrackEmbeddingMetadata:
    track_id: int
    point_id: str
    model_name: str
    model_version: Optional[str]
    vector_dimensions: int


class PositionQualityError(RuntimeError):
    pass


def run_position_job(track_id: str):
    logger.info("run_position_job: starting for track %s", track_id)
    ensure_positioning_schema()
    logger.info("run_position_job: schema ready")
    positioner = UMAPPositioner()
    logger.info("run_position_job: UMAPPositioner created")
    track_id_int = int(track_id)
    target = get_track_embedding_metadata(track_id_int)
    logger.info("run_position_job: embedding metadata = %s", target)
    if target is None:
        logger.error("No embedding metadata for track %s", track_id)
        return None

    new_embedding = get_embedding_vector(target.point_id)
    logger.info("run_position_job: got embedding vector = %s", new_embedding is not None)
    if new_embedding is None:
        logger.error("No Qdrant vector for track %s", track_id)
        return None

    all_embeddings, all_ids = get_compatible_embeddings(target, limit=UMAP_MAX_TRACKS)
    logger.info("run_position_job: compatible embeddings = %d", len(all_ids))
    if not len(all_ids) or track_id_int not in all_ids:
        logger.error("Track %s is missing from the compatible embedding set", track_id)
        return None

    pending_count = get_unpositioned_count(target)
    logger.info("run_position_job: pending_count = %d", pending_count)
    should_recalculate = pending_count >= UMAP_RECALC_INTERVAL or len(all_ids) < 15
    logger.info("run_position_job: should_recalculate = %s", should_recalculate)
    result = None

    if should_recalculate:
        try:
            result = recalculate_full_map(positioner, target, all_embeddings, all_ids)
        except PositionQualityError as exc:
            logger.warning("Full UMAP map rejected: %s", exc)
            result = approximate_track_position(
                positioner,
                target,
                new_embedding,
                all_embeddings,
                all_ids,
            )
        if result is None:
            result = approximate_track_position(
                positioner,
                target,
                new_embedding,
                all_embeddings,
                all_ids,
            )
    else:
        result = approximate_track_position(
            positioner,
            target,
            new_embedding,
            all_embeddings,
            all_ids,
        )
        if result is None:
            try:
                result = recalculate_full_map(positioner, target, all_embeddings, all_ids)
            except PositionQualityError as exc:
                logger.warning("Full UMAP map rejected after KNN fallback: %s", exc)

    if result is None:
        return None

    publish_ws_event(
        "track_positioned",
        {
            "track_id": track_id_int,
            "x": result["x"],
            "y": result["y"],
            "z": result["z"],
            "position_method": result["position_method"],
            "position_version_id": result.get("position_version_id"),
        },
    )
    return result


def recalculate_full_map(
    positioner: UMAPPositioner,
    target: TrackEmbeddingMetadata,
    embeddings: np.ndarray,
    track_ids: List[int],
) -> Optional[Dict[str, object]]:
    if len(track_ids) < 5:
        return None
    started_at = time.time()
    positions = positioner.fit_transform(embeddings)
    anchors = get_anchor_positions(track_ids)
    anchor_indices = np.asarray(
        [index for index, track_id in enumerate(track_ids) if track_id in anchors],
        dtype=np.int64,
    )
    if len(anchor_indices) >= 3:
        anchor_positions = np.asarray([anchors[track_ids[index]] for index in anchor_indices], dtype=np.float32)
        positions = positioner.align_to_anchors(positions, anchor_indices, anchor_positions)

    metrics = positioner.quality_metrics(embeddings, positions, n_neighbors=UMAP_QUALITY_K)
    metrics.update(
        {
            "anchor_count": int(len(anchor_indices)),
            "duration_ms": int((time.time() - started_at) * 1000),
        }
    )
    fingerprint = catalog_fingerprint(track_ids, embeddings, target)
    if (
        metrics["trustworthiness"] < UMAP_MIN_TRUSTWORTHINESS
        or metrics["neighbor_recall"] < UMAP_MIN_NEIGHBOR_RECALL
    ):
        reason = (
            f"quality below threshold: trustworthiness={metrics['trustworthiness']:.4f}, "
            f"neighbor_recall={metrics['neighbor_recall']:.4f}"
        )
        record_rejected_map(target, len(track_ids), metrics, fingerprint, reason)
        raise PositionQualityError(reason)

    version_id = publish_full_map(target, track_ids, positions, metrics, fingerprint)
    target_index = track_ids.index(target.track_id)
    x, y, z = map(float, positions[target_index])
    logger.info(
        "Published full UMAP map %s: %s tracks in %sms",
        version_id,
        len(track_ids),
        metrics["duration_ms"],
    )
    return {
        "x": x,
        "y": y,
        "z": z,
        "position_method": "clap_umap_full",
        "position_version_id": version_id,
        "position_quality": metrics,
    }


def approximate_track_position(
    positioner: UMAPPositioner,
    target: TrackEmbeddingMetadata,
    new_embedding: np.ndarray,
    embeddings: np.ndarray,
    track_ids: List[int],
) -> Optional[Dict[str, object]]:
    candidate_embeddings, candidate_positions, candidate_ids = get_positioned_embedding_subset(
        embeddings,
        track_ids,
        exclude_track_id=target.track_id,
    )
    if len(candidate_ids) < UMAP_KNN_MIN_NEIGHBORS:
        logger.info(
            "KNN position unavailable for track %s: only %s valid neighbors",
            target.track_id,
            len(candidate_ids),
        )
        return None
    try:
        neighbor_result = positioner.nearest_neighbor_position_with_details(
            new_embedding,
            candidate_embeddings,
            candidate_positions,
            k=UMAP_KNN_K,
            min_similarity=UMAP_KNN_MIN_SIMILARITY,
            min_neighbors=UMAP_KNN_MIN_NEIGHBORS,
        )
    except ValueError as exc:
        logger.info("KNN position unavailable for track %s: %s", target.track_id, exc)
        return None

    neighbor_ids = [candidate_ids[index] for index in neighbor_result.neighbor_indices]
    quality = {
        "neighbor_track_ids": neighbor_ids,
        "neighbor_similarities": [float(value) for value in neighbor_result.similarities],
        "min_similarity": UMAP_KNN_MIN_SIMILARITY,
    }
    version_id = get_current_published_version()
    x, y, z = map(float, neighbor_result.position)
    update_track_position(
        target.track_id,
        x,
        y,
        z,
        method="clap_knn_approx",
        version_id=version_id,
        quality=quality,
    )
    logger.info("Published KNN position for track %s from %s neighbors", target.track_id, len(neighbor_ids))
    return {
        "x": x,
        "y": y,
        "z": z,
        "position_method": "clap_knn_approx",
        "position_version_id": version_id,
        "position_quality": quality,
    }


def ensure_positioning_schema() -> None:
    global _POSITIONING_SCHEMA_READY
    if _POSITIONING_SCHEMA_READY:
        return
    migration_path = PIPELINE_ROOT / "database" / "migrations" / "20260808_positioning_v1.sql"
    migration_sql = migration_path.read_text()
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(migration_sql)
        conn.commit()
        _POSITIONING_SCHEMA_READY = True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_track_embedding_metadata(track_id: int) -> Optional[TrackEmbeddingMetadata]:
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT track_id, qdrant_point_id, model_name, model_version, vector_dimensions
                FROM embeddings
                WHERE track_id = %s
                LIMIT 1
                """,
                (track_id,),
            )
            row = cursor.fetchone()
    finally:
        conn.close()
    if not row or not row[1]:
        return None
    return TrackEmbeddingMetadata(
        track_id=int(row[0]),
        point_id=str(row[1]),
        model_name=str(row[2]),
        model_version=row[3],
        vector_dimensions=int(row[4]),
    )


def get_embedding_vector(point_id: str) -> Optional[np.ndarray]:
    client = _get_qdrant_client()
    if not client:
        return None
    points = client.retrieve(collection_name=QDRANT_COLLECTION, ids=[point_id], with_vectors=True)
    if not points or getattr(points[0], "vector", None) is None:
        return None
    vector = np.asarray(points[0].vector, dtype=np.float32)
    return vector if vector.ndim == 1 else None


def get_compatible_embeddings(
    target: TrackEmbeddingMetadata,
    limit: int = UMAP_MAX_TRACKS,
) -> Tuple[np.ndarray, List[int]]:
    client = _get_qdrant_client()
    if not client:
        return np.empty((0, target.vector_dimensions), dtype=np.float32), []
    points, _ = client.scroll(
        collection_name=QDRANT_COLLECTION,
        limit=limit,
        with_payload=True,
        with_vectors=True,
    )
    candidates = []
    for point in points or []:
        payload = getattr(point, "payload", None) or {}
        vector = getattr(point, "vector", None)
        try:
            track_id = int(payload.get("track_id"))
        except (TypeError, ValueError):
            continue
        vector_array = np.asarray(vector, dtype=np.float32)
        if vector_array.ndim == 1 and vector_array.size == target.vector_dimensions:
            candidates.append((track_id, str(point.id), vector_array))
    if not candidates:
        return np.empty((0, target.vector_dimensions), dtype=np.float32), []

    candidate_ids = [track_id for track_id, _, _ in candidates]
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT track_id, qdrant_point_id
                FROM embeddings
                WHERE track_id = ANY(%s)
                  AND model_name = %s
                  AND model_version IS NOT DISTINCT FROM %s
                  AND vector_dimensions = %s
                """,
                (
                    candidate_ids,
                    target.model_name,
                    target.model_version,
                    target.vector_dimensions,
                ),
            )
            compatible_points = {int(row[0]): str(row[1]) for row in cursor.fetchall() if row[1]}
    finally:
        conn.close()

    filtered = [
        (track_id, vector)
        for track_id, point_id, vector in candidates
        if compatible_points.get(track_id) == point_id
    ]
    filtered.sort(key=lambda entry: entry[0])
    if not filtered:
        return np.empty((0, target.vector_dimensions), dtype=np.float32), []
    return np.vstack([vector for _, vector in filtered]), [track_id for track_id, _ in filtered]


def get_positioned_embedding_subset(
    embeddings: np.ndarray,
    track_ids: Sequence[int],
    exclude_track_id: int,
) -> Tuple[np.ndarray, np.ndarray, List[int]]:
    eligible_ids = [track_id for track_id in track_ids if track_id != exclude_track_id]
    if not eligible_ids:
        return np.empty((0, embeddings.shape[1]), dtype=np.float32), np.empty((0, 3), dtype=np.float32), []
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, position_x, position_y, position_z
                FROM tracks
                WHERE id = ANY(%s)
                  AND position_x IS NOT NULL
                  AND position_y IS NOT NULL
                  AND position_z IS NOT NULL
                  AND position_method = ANY(%s)
                """,
                (eligible_ids, list(VALID_CLAP_POSITION_METHODS)),
            )
            positioned = {
                int(row[0]): np.asarray(row[1:4], dtype=np.float32)
                for row in cursor.fetchall()
                if np.isfinite(np.asarray(row[1:4], dtype=np.float32)).all()
            }
    finally:
        conn.close()
    selected_indices = [
        index
        for index, track_id in enumerate(track_ids)
        if track_id != exclude_track_id and track_id in positioned
    ]
    selected_ids = [track_ids[index] for index in selected_indices]
    if not selected_indices:
        return np.empty((0, embeddings.shape[1]), dtype=np.float32), np.empty((0, 3), dtype=np.float32), []
    return (
        embeddings[selected_indices],
        np.vstack([positioned[track_id] for track_id in selected_ids]),
        selected_ids,
    )


def get_anchor_positions(track_ids: Sequence[int]) -> Dict[int, np.ndarray]:
    if not track_ids:
        return {}
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, position_x, position_y, position_z
                FROM tracks
                WHERE id = ANY(%s)
                  AND position_x IS NOT NULL
                  AND position_y IS NOT NULL
                  AND position_z IS NOT NULL
                  AND position_method = ANY(%s)
                """,
                (list(track_ids), list(FULL_POSITION_METHODS)),
            )
            rows = cursor.fetchall()
    finally:
        conn.close()
    return {
        int(row[0]): np.asarray(row[1:4], dtype=np.float32)
        for row in rows
        if np.isfinite(np.asarray(row[1:4], dtype=np.float32)).all()
    }


def get_unpositioned_count(target: TrackEmbeddingMetadata) -> int:
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT(*)
                FROM tracks t
                JOIN embeddings e ON e.track_id = t.id
                WHERE e.model_name = %s
                  AND e.model_version IS NOT DISTINCT FROM %s
                  AND e.vector_dimensions = %s
                  AND (
                      t.position_x IS NULL
                      OR t.position_y IS NULL
                      OR t.position_z IS NULL
                      OR t.position_method IS NULL
                      OR NOT (t.position_method = ANY(%s))
                  )
                """,
                (
                    target.model_name,
                    target.model_version,
                    target.vector_dimensions,
                    list(VALID_CLAP_POSITION_METHODS),
                ),
            )
            count = cursor.fetchone()[0]
    finally:
        conn.close()
    return int(count)


def publish_full_map(
    target: TrackEmbeddingMetadata,
    track_ids: Sequence[int],
    positions: np.ndarray,
    metrics: Dict[str, object],
    fingerprint: str,
) -> str:
    version_id = str(uuid.uuid4())
    rows = [
        (version_id, int(track_id), float(position[0]), float(position[1]), float(position[2]))
        for track_id, position in zip(track_ids, positions)
    ]
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtext('rebel_sonic_map_publish'))")
            cursor.execute(
                """
                INSERT INTO sonic_map_versions (
                    id, status, method, model_name, model_version, vector_dimensions,
                    track_count, umap_params, metrics, catalog_fingerprint
                )
                VALUES (%s, 'staging', 'clap_umap_full', %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    version_id,
                    target.model_name,
                    target.model_version,
                    target.vector_dimensions,
                    len(track_ids),
                    Json(umap_params_for_count(len(track_ids))),
                    Json(metrics),
                    fingerprint,
                ),
            )
            execute_values(
                cursor,
                """
                INSERT INTO sonic_map_positions_staging (
                    version_id, track_id, position_x, position_y, position_z
                ) VALUES %s
                """,
                rows,
            )
            cursor.execute(
                "UPDATE sonic_map_versions SET status = 'superseded' WHERE status = 'published'"
            )
            cursor.execute(
                """
                UPDATE tracks t
                SET position_x = s.position_x,
                    position_y = s.position_y,
                    position_z = s.position_z,
                    position_method = 'clap_umap_full',
                    position_version_id = %s,
                    positioned_at = NOW(),
                    position_quality = %s,
                    updated_at = NOW()
                FROM sonic_map_positions_staging s
                WHERE s.version_id = %s
                  AND s.track_id = t.id
                """,
                (version_id, Json(metrics), version_id),
            )
            cursor.execute(
                """
                UPDATE sonic_map_versions
                SET status = 'published', published_at = NOW()
                WHERE id = %s
                """,
                (version_id,),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return version_id


def record_rejected_map(
    target: TrackEmbeddingMetadata,
    track_count: int,
    metrics: Dict[str, object],
    fingerprint: str,
    reason: str,
) -> str:
    version_id = str(uuid.uuid4())
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO sonic_map_versions (
                    id, status, method, model_name, model_version, vector_dimensions,
                    track_count, umap_params, metrics, catalog_fingerprint, failure_reason
                )
                VALUES (%s, 'rejected', 'clap_umap_full', %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    version_id,
                    target.model_name,
                    target.model_version,
                    target.vector_dimensions,
                    track_count,
                    Json(umap_params_for_count(track_count)),
                    Json(metrics),
                    fingerprint,
                    reason,
                ),
            )
        conn.commit()
    finally:
        conn.close()
    return version_id


def update_track_position(
    track_id: int,
    x: float,
    y: float,
    z: float,
    method: str,
    version_id: Optional[str],
    quality: Dict[str, object],
) -> None:
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
                    position_version_id = %s,
                    positioned_at = NOW(),
                    position_quality = %s,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (float(x), float(y), float(z), method, version_id, Json(quality), track_id),
            )
        conn.commit()
    finally:
        conn.close()


def get_current_published_version() -> Optional[str]:
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id
                FROM sonic_map_versions
                WHERE status = 'published'
                ORDER BY published_at DESC NULLS LAST, created_at DESC
                LIMIT 1
                """
            )
            row = cursor.fetchone()
    finally:
        conn.close()
    return str(row[0]) if row else None


def catalog_fingerprint(
    track_ids: Sequence[int],
    embeddings: np.ndarray,
    target: TrackEmbeddingMetadata,
) -> str:
    digest = hashlib.sha256()
    digest.update(target.model_name.encode("utf-8"))
    digest.update((target.model_version or "").encode("utf-8"))
    digest.update(str(target.vector_dimensions).encode("ascii"))
    digest.update(",".join(str(track_id) for track_id in track_ids).encode("ascii"))
    digest.update(np.asarray(embeddings, dtype=np.float32).tobytes())
    return digest.hexdigest()


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
        from qdrant_client import QdrantClient
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
        from redis import Redis
    except ImportError:
        logger.warning("redis not installed; cannot publish WS events")
        return None
    try:
        _REDIS_CLIENT = Redis.from_url(REDIS_URL)
    except Exception as exc:
        logger.warning("Could not connect to Redis (%s); cannot publish WS events", exc)
        _REDIS_CLIENT = None
    return _REDIS_CLIENT


__all__ = [
    "PositionQualityError",
    "TrackEmbeddingMetadata",
    "approximate_track_position",
    "catalog_fingerprint",
    "ensure_positioning_schema",
    "get_compatible_embeddings",
    "get_positioned_embedding_subset",
    "publish_full_map",
    "recalculate_full_map",
    "run_position_job",
]
