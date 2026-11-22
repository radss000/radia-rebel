"""CLAP similarity search backed by Qdrant and PostgreSQL metadata."""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from psycopg2.extras import RealDictCursor

from database.utils import get_db_connection

QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "music_embeddings")
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
QDRANT_SIMILARITY_TIMEOUT = int(os.getenv("QDRANT_SIMILARITY_TIMEOUT", "5"))
MAX_CANDIDATE_POINTS = int(os.getenv("SIMILARITY_MAX_CANDIDATES", "1000"))
PIPELINE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CALIBRATION_PATH = PIPELINE_ROOT / "config" / "similarity_thresholds.v1.json"

_QDRANT_CLIENT = None


class SimilarityServiceError(RuntimeError):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass(frozen=True)
class EmbeddingMetadata:
    track_id: int
    qdrant_point_id: str
    model_name: str
    model_version: Optional[str]
    vector_dimensions: int
    position_x: Optional[float]
    position_y: Optional[float]
    position_z: Optional[float]


def get_qdrant_client():
    global _QDRANT_CLIENT
    if _QDRANT_CLIENT is not None:
        return _QDRANT_CLIENT
    try:
        from qdrant_client import QdrantClient
    except ImportError as exc:
        raise SimilarityServiceError(503, "Qdrant client is not installed") from exc
    try:
        _QDRANT_CLIENT = QdrantClient(
            host=QDRANT_HOST,
            port=QDRANT_PORT,
            api_key=QDRANT_API_KEY,
            timeout=QDRANT_SIMILARITY_TIMEOUT,
        )
    except Exception as exc:
        raise SimilarityServiceError(503, f"Qdrant client initialization failed: {exc}") from exc
    return _QDRANT_CLIENT


def _load_target_embedding(conn, track_id: int) -> EmbeddingMetadata:
    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """
            SELECT
                t.id AS track_id,
                t.position_x,
                t.position_y,
                t.position_z,
                e.qdrant_point_id,
                e.model_name,
                e.model_version,
                e.vector_dimensions
            FROM tracks t
            LEFT JOIN embeddings e ON e.track_id = t.id
            WHERE t.id = %s
            LIMIT 1
            """,
            (track_id,),
        )
        row = cursor.fetchone()
    if not row:
        raise SimilarityServiceError(404, "Track not found")
    if not row.get("qdrant_point_id"):
        raise SimilarityServiceError(409, "Track does not have a searchable embedding")
    if not row.get("model_name") or not row.get("vector_dimensions"):
        raise SimilarityServiceError(409, "Track embedding metadata is incomplete")
    return EmbeddingMetadata(
        track_id=int(row["track_id"]),
        qdrant_point_id=str(row["qdrant_point_id"]),
        model_name=str(row["model_name"]),
        model_version=row.get("model_version"),
        vector_dimensions=int(row["vector_dimensions"]),
        position_x=row.get("position_x"),
        position_y=row.get("position_y"),
        position_z=row.get("position_z"),
    )


def _load_candidate_tracks(conn, track_ids: Sequence[int]) -> Dict[int, Dict[str, Any]]:
    if not track_ids:
        return {}
    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """
            SELECT
                t.id,
                t.title,
                t.artist,
                t.album,
                t.genre,
                t.year,
                t.preview_url,
                t.position_x,
                t.position_y,
                t.position_z,
                t.position_method,
                t.position_version_id,
                t.positioned_at,
                t.position_quality,
                e.model_name,
                e.model_version,
                e.vector_dimensions
            FROM tracks t
            JOIN embeddings e ON e.track_id = t.id
            WHERE t.id = ANY(%s)
            """,
            (list(track_ids),),
        )
        rows = cursor.fetchall()
    return {int(row["id"]): dict(row) for row in rows}


def _point_track_id(point: Any) -> Optional[int]:
    payload = getattr(point, "payload", None) or {}
    value = payload.get("track_id")
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _compatible_embedding(row: Mapping[str, Any], target: EmbeddingMetadata) -> bool:
    return (
        row.get("model_name") == target.model_name
        and row.get("model_version") == target.model_version
        and int(row.get("vector_dimensions") or 0) == target.vector_dimensions
    )


def _distance_3d(target: EmbeddingMetadata, row: Mapping[str, Any]) -> Optional[float]:
    target_position = (target.position_x, target.position_y, target.position_z)
    candidate_position = (row.get("position_x"), row.get("position_y"), row.get("position_z"))
    if any(value is None for value in target_position + candidate_position):
        return None
    return math.sqrt(
        sum((float(candidate) - float(origin)) ** 2 for origin, candidate in zip(target_position, candidate_position))
    )


def _validated_thresholds(values: Mapping[str, Any]) -> Optional[Dict[str, float]]:
    try:
        thresholds = {
            "very_close": float(values["very_close"]),
            "close": float(values["close"]),
            "related": float(values["related"]),
        }
    except (KeyError, TypeError, ValueError):
        return None
    if not 1.0 >= thresholds["very_close"] >= thresholds["close"] >= thresholds["related"] >= -1.0:
        return None
    return thresholds


def load_similarity_calibration() -> Optional[Dict[str, Any]]:
    names = {
        "very_close": "SIMILARITY_VERY_CLOSE_THRESHOLD",
        "close": "SIMILARITY_CLOSE_THRESHOLD",
        "related": "SIMILARITY_RELATED_THRESHOLD",
    }
    if all(os.getenv(env_name) for env_name in names.values()):
        thresholds = _validated_thresholds(
            {name: os.environ[env_name] for name, env_name in names.items()}
        )
        return {"source": "environment", "thresholds": thresholds} if thresholds else None

    configured_path = os.getenv("SIMILARITY_CALIBRATION_PATH")
    calibration_path = Path(configured_path).expanduser() if configured_path else DEFAULT_CALIBRATION_PATH
    if not calibration_path.is_absolute():
        calibration_path = PIPELINE_ROOT / calibration_path
    if not calibration_path.exists():
        return None
    try:
        calibration = json.loads(calibration_path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if calibration.get("schema_version") != 1 or calibration.get("active") is not True:
        return None
    thresholds = _validated_thresholds(calibration.get("thresholds") or {})
    if not thresholds:
        return None
    return {
        "source": "versioned_config",
        "calibration_id": calibration.get("calibration_id"),
        "corpus_id": calibration.get("corpus_id"),
        "corpus_version": calibration.get("corpus_version"),
        "model_name": calibration.get("model_name"),
        "model_version": calibration.get("model_version"),
        "vector_dimensions": calibration.get("vector_dimensions"),
        "thresholds": thresholds,
    }


def _similarity_thresholds() -> Optional[Dict[str, float]]:
    calibration = load_similarity_calibration()
    return calibration["thresholds"] if calibration else None


def classify_similarity(score: float, thresholds: Optional[Mapping[str, float]] = None) -> Optional[str]:
    thresholds = thresholds or _similarity_thresholds()
    if not thresholds:
        return None
    if score >= thresholds["very_close"]:
        return "very_close"
    if score >= thresholds["close"]:
        return "close"
    if score >= thresholds["related"]:
        return "related"
    return "weak"


def build_similarity_results(
    points: Iterable[Any],
    candidate_rows: Mapping[int, Mapping[str, Any]],
    target: EmbeddingMetadata,
    limit: int,
    offset: int,
    min_score: float,
) -> List[Dict[str, Any]]:
    compatible: List[tuple[float, int, Mapping[str, Any]]] = []
    seen_track_ids = set()
    for point in points:
        candidate_id = _point_track_id(point)
        if candidate_id is None or candidate_id == target.track_id or candidate_id in seen_track_ids:
            continue
        score = float(getattr(point, "score", 0.0))
        if score < min_score:
            continue
        row = candidate_rows.get(candidate_id)
        if not row or not _compatible_embedding(row, target):
            continue
        seen_track_ids.add(candidate_id)
        compatible.append((score, candidate_id, row))

    compatible.sort(key=lambda entry: (-entry[0], entry[1]))
    selected = compatible[offset : offset + limit]
    thresholds = _similarity_thresholds()
    results = []
    for index, (score, candidate_id, row) in enumerate(selected, start=offset + 1):
        results.append(
            {
                "track_id": candidate_id,
                "title": row.get("title"),
                "artist": row.get("artist"),
                "album": row.get("album"),
                "genre": row.get("genre"),
                "year": row.get("year"),
                "preview_url": row.get("preview_url"),
                "similarity_score": score,
                "similarity_band": classify_similarity(score, thresholds),
                "rank": index,
                "model_name": row.get("model_name"),
                "model_version": row.get("model_version"),
                "vector_dimensions": row.get("vector_dimensions"),
                "position": {
                    "x": row.get("position_x"),
                    "y": row.get("position_y"),
                    "z": row.get("position_z"),
                },
                "position_method": row.get("position_method"),
                "position_version_id": (
                    str(row.get("position_version_id")) if row.get("position_version_id") else None
                ),
                "positioned_at": row.get("positioned_at"),
                "position_quality": row.get("position_quality") or {},
                "distance_3d": _distance_3d(target, row),
            }
        )
    return results


def find_similar_tracks(track_id: int, limit: int, offset: int, min_score: float) -> Dict[str, Any]:
    conn = get_db_connection()
    try:
        target = _load_target_embedding(conn, track_id)
        client = get_qdrant_client()
        try:
            points = client.retrieve(
                collection_name=QDRANT_COLLECTION,
                ids=[target.qdrant_point_id],
                with_vectors=True,
            )
        except Exception as exc:
            raise SimilarityServiceError(503, f"Qdrant retrieve failed: {exc}") from exc
        if not points or getattr(points[0], "vector", None) is None:
            raise SimilarityServiceError(409, "Embedding metadata points to a missing Qdrant vector")

        requested_candidates = max((offset + limit) * 5 + 1, limit + 1)
        candidate_limit = min(requested_candidates, MAX_CANDIDATE_POINTS)
        try:
            response = client.query_points(
                collection_name=QDRANT_COLLECTION,
                query=points[0].vector,
                limit=candidate_limit,
                with_payload=True,
                with_vectors=False,
                score_threshold=min_score,
                timeout=QDRANT_SIMILARITY_TIMEOUT,
            )
        except Exception as exc:
            raise SimilarityServiceError(503, f"Qdrant similarity search failed: {exc}") from exc

        scored_points = list(getattr(response, "points", []) or [])
        candidate_ids = [candidate_id for point in scored_points if (candidate_id := _point_track_id(point)) is not None]
        candidate_rows = _load_candidate_tracks(conn, candidate_ids)
        results = build_similarity_results(
            scored_points,
            candidate_rows,
            target,
            limit=limit,
            offset=offset,
            min_score=min_score,
        )
        calibration = load_similarity_calibration()
        thresholds = calibration["thresholds"] if calibration else None
        return {
            "track_id": target.track_id,
            "model_name": target.model_name,
            "model_version": target.model_version,
            "vector_dimensions": target.vector_dimensions,
            "metric": "cosine",
            "limit": limit,
            "offset": offset,
            "min_score": min_score,
            "count": len(results),
            "calibration_status": "configured" if calibration else "unconfigured",
            "calibration": calibration,
            "results": results,
        }
    finally:
        conn.close()


__all__ = [
    "EmbeddingMetadata",
    "SimilarityServiceError",
    "build_similarity_results",
    "classify_similarity",
    "find_similar_tracks",
    "get_qdrant_client",
    "load_similarity_calibration",
]
