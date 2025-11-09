#!/usr/bin/env python3
"""
Backfill analysis jobs for tracks using the real audio worker.

This CLI inspects the tracks/audio_assets tables, figures out which jobs are
still missing (preview cache, audio features, embedding, position), and
enqueues them through the shared Redis/RQ queue so the existing workers can
process them asynchronously.
"""

from __future__ import annotations

import argparse
import logging
from typing import Iterable, List

import psycopg2
from psycopg2.extras import RealDictCursor

from database.utils import DB_CONFIG
from jobs.queue import enqueue_analysis_job

logger = logging.getLogger("analysis_backfill")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

DEFAULT_STEPS = ("preview_fetch", "audio_features", "embedding", "position")
ACTIVE_STATUSES = {"queued", "running"}


def fetch_candidates(conn, limit: int) -> List[dict]:
    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """
            SELECT
                t.id AS track_id,
                t.title,
                t.artist,
                t.energy,
                t.danceability,
                t.acousticness,
                t.bass,
                t.brightness,
                t.valence,
                t.bpm,
                t.embedding_id,
                t.position_x,
                t.position_y,
                t.position_z,
                aa.id AS audio_asset_id,
                aa.fetch_status,
                aa.storage_path,
                aa.provider_type,
                aa.provider_track_id
            FROM audio_assets aa
            JOIN tracks t ON t.id = aa.track_id
            WHERE aa.deleted_at IS NULL
            ORDER BY t.updated_at DESC NULLS LAST
            LIMIT %s
            """,
            (limit,),
        )
        return cursor.fetchall()


def job_is_pending(conn, job_type: str, track_id: int | None, audio_asset_id: str | None) -> bool:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT 1
            FROM analysis_jobs
            WHERE job_type = %s
              AND status = ANY(%s)
              AND (%s::int IS NULL OR track_id = %s)
              AND (%s::uuid IS NULL OR audio_asset_id = %s::uuid)
            LIMIT 1
            """,
            (
                job_type,
                list(ACTIVE_STATUSES),
                track_id,
                track_id,
                audio_asset_id,
                audio_asset_id,
            ),
        )
        return cursor.fetchone() is not None


def needs_features(row: dict) -> bool:
    fields = ("energy", "danceability", "acousticness", "bass", "brightness", "valence", "bpm")
    return any(row.get(field) is None for field in fields)


def determine_jobs(row: dict, requested_steps: Iterable[str]) -> List[str]:
    jobs: List[str] = []
    if "preview_fetch" in requested_steps:
        if not row.get("storage_path") or row.get("fetch_status") != "fetched":
            jobs.append("preview_fetch")
    if "audio_features" in requested_steps and needs_features(row):
        jobs.append("audio_features")
    if "embedding" in requested_steps and row.get("embedding_id") is None:
        jobs.append("embedding")
    if "position" in requested_steps and row.get("position_x") is None:
        jobs.append("position")
    return jobs


def enqueue_row_jobs(row: dict, job_types: Iterable[str], requested_by: str, dry_run: bool, conn) -> None:
    for job_type in job_types:
        track_id = row.get("track_id")
        audio_asset_id = row.get("audio_asset_id")
        asset_required = job_type in {"preview_fetch", "audio_features", "embedding"}
        if asset_required and not audio_asset_id:
            logger.warning("Track %s has no audio asset; skipping %s", track_id, job_type)
            continue

        if job_is_pending(
            conn,
            job_type,
            track_id if job_type in {"audio_features", "embedding", "position"} else None,
            audio_asset_id if asset_required else None,
        ):
            logger.debug("Track %s already has a pending %s job", track_id, job_type)
            continue

        if dry_run:
            logger.info("[dry-run] Would enqueue %s for track=%s asset=%s", job_type, track_id, audio_asset_id)
            continue

        job_row, _ = enqueue_analysis_job(
            job_type=job_type,
            track_id=track_id if job_type in {"audio_features", "embedding", "position"} else None,
            audio_asset_id=str(audio_asset_id) if audio_asset_id and asset_required else None,
            provider_type=row.get("provider_type"),
            provider_track_id=row.get("provider_track_id"),
            requested_by=requested_by,
        )
        logger.info("Enqueued %s for track %s (job %s)", job_type, track_id, job_row["id"])


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill analysis jobs using cached audio previews.")
    parser.add_argument(
        "--steps",
        default=",".join(DEFAULT_STEPS),
        help="Comma-separated list of steps to enqueue (default: preview_fetch,audio_features,embedding,position)",
    )
    parser.add_argument("--limit", type=int, default=200, help="Maximum number of tracks to inspect")
    parser.add_argument("--dry-run", action="store_true", help="Log actions without enqueuing jobs")
    parser.add_argument(
        "--requested-by",
        default="backfill-cli",
        help="Value stored in analysis_jobs.requested_by for traceability",
    )
    args = parser.parse_args()

    requested_steps = tuple(step.strip() for step in args.steps.split(",") if step.strip())
    invalid = set(requested_steps) - set(DEFAULT_STEPS)
    if invalid:
        raise SystemExit(f"Invalid step(s): {', '.join(sorted(invalid))}. Supported: {', '.join(DEFAULT_STEPS)}")

    conn = psycopg2.connect(**DB_CONFIG)
    try:
        candidates = fetch_candidates(conn, args.limit)
        if not candidates:
            logger.info("No tracks with audio assets found.")
            return
        logger.info("Scanning %s tracks for missing jobs (%s)", len(candidates), ", ".join(requested_steps))
        for row in candidates:
            jobs = determine_jobs(row, requested_steps)
            if not jobs:
                continue
            enqueue_row_jobs(row, jobs, args.requested_by, args.dry_run, conn)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
