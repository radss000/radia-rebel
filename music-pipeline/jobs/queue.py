"""Shared helpers to insert and enqueue analysis jobs."""

from __future__ import annotations

import os
from typing import Any, Dict, Optional, Tuple

from psycopg2.extras import Json, RealDictCursor
from redis import Redis
from rq import Queue

from database.utils import get_db_connection
from jobs.tasks import JOB_TASK_MAP

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
ANALYSIS_QUEUE_NAME = os.getenv("ANALYSIS_QUEUE_NAME", "analysis")

redis_connection = Redis.from_url(REDIS_URL)
analysis_queue = Queue(ANALYSIS_QUEUE_NAME, connection=redis_connection)

DEFAULT_JOB_TIMEOUT = int(os.getenv("JOB_TIMEOUT_DEFAULT", "300"))
EMBEDDING_JOB_TIMEOUT = int(os.getenv("EMBEDDING_JOB_TIMEOUT", "1200"))

JOB_TIMEOUTS = {
    "preview_fetch": DEFAULT_JOB_TIMEOUT,
    "audio_features": DEFAULT_JOB_TIMEOUT,
    "embedding": EMBEDDING_JOB_TIMEOUT,
    "position": DEFAULT_JOB_TIMEOUT,
}


def serialize_job(row: Dict[str, Any]) -> Dict[str, Any]:
    """Convert DB row values into JSON-serialisable primitives."""
    from datetime import datetime
    from uuid import UUID

    serialized: Dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, datetime):
            serialized[key] = value.isoformat()
        elif isinstance(value, UUID):
            serialized[key] = str(value)
        else:
            serialized[key] = value
    return serialized


def enqueue_analysis_job(
    *,
    job_type: str,
    track_id: Optional[int] = None,
    audio_asset_id: Optional[str] = None,
    provider_type: Optional[str] = None,
    provider_track_id: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
    priority: int = 0,
    requested_by: Optional[str] = None,
    job_timeout: Optional[int] = None,
) -> Tuple[Dict[str, Any], str]:
    """Insert an analysis_job row then push it to the RQ queue."""
    task_path = JOB_TASK_MAP.get(job_type)
    if not task_path:
        raise ValueError(f"Unsupported job_type '{job_type}'")

    conn = get_db_connection()
    job_row: Optional[Dict[str, Any]] = None
    try:
        with conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    """
                    INSERT INTO analysis_jobs (
                        track_id,
                        audio_asset_id,
                        job_type,
                        status,
                        priority,
                        provider_type,
                        provider_track_id,
                        payload,
                        requested_by
                    ) VALUES (
                        %(track_id)s,
                        %(audio_asset_id)s,
                        %(job_type)s,
                        'queued',
                        %(priority)s,
                        %(provider_type)s,
                        %(provider_track_id)s,
                        %(payload)s,
                        %(requested_by)s
                    )
                    RETURNING *
                    """,
                    {
                        "track_id": track_id,
                        "audio_asset_id": audio_asset_id,
                        "job_type": job_type,
                        "priority": priority,
                        "provider_type": provider_type,
                        "provider_track_id": provider_track_id,
                        "payload": Json(payload) if payload is not None else None,
                        "requested_by": requested_by,
                    },
                )
                job_row = cursor.fetchone()
    finally:
        conn.close()

    assert job_row is not None  # for mypy

    timeout_value = job_timeout or JOB_TIMEOUTS.get(job_type, DEFAULT_JOB_TIMEOUT)

    try:
        rq_job = analysis_queue.enqueue(
            task_path,
            str(job_row["id"]),
            job_id=str(job_row["id"]),
            job_timeout=timeout_value,
        )
    except Exception as exc:
        conn = get_db_connection()
        with conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE analysis_jobs SET status = 'failed', error_message = %s WHERE id = %s",
                    (f"Queue enqueue failed: {exc}", job_row["id"]),
                )
        conn.close()
        raise RuntimeError(f"Failed to enqueue job: {exc}") from exc

    return job_row, rq_job.id


__all__ = ["analysis_queue", "enqueue_analysis_job", "serialize_job"]
