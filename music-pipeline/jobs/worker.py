#!/usr/bin/env python3
from __future__ import annotations

import multiprocessing

"""RQ worker for analysis jobs."""

multiprocessing.set_start_method("spawn", force=True)

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv
from redis import Redis
from rq import Queue, SimpleWorker
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
QUEUE_NAME = os.getenv("ANALYSIS_QUEUE_NAME", "analysis")
POSITION_QUEUE_NAME = os.getenv("POSITION_QUEUE_NAME", "positioning")


def _parse_queues() -> list[str]:
    parser = argparse.ArgumentParser(description="REBEL analysis worker")
    parser.add_argument(
        "--queues",
        default=os.getenv("WORKER_QUEUES", f"{QUEUE_NAME},{POSITION_QUEUE_NAME}"),
        help=(
            "Comma-separated queues to consume. Production: one worker with "
            f"'{QUEUE_NAME}' (preview/features/CLAP) and one with '{POSITION_QUEUE_NAME}' "
            "(UMAP), so torch and scikit-learn OpenMP runtimes never share a process. "
            "Default consumes both (single-worker dev setup)."
        ),
    )
    args = parser.parse_args()
    queues = [name.strip() for name in args.queues.split(",") if name.strip()]
    if not queues:
        parser.error("--queues must name at least one queue")
    return queues


def main() -> None:
    queue_names = _parse_queues()
    pipeline_root = Path(__file__).resolve().parents[1]
    pipeline_env = pipeline_root / ".env"
    repo_env = pipeline_root.parent / ".env"
    if pipeline_env.exists():
        load_dotenv(dotenv_path=pipeline_env, override=False)
    if repo_env.exists():
        load_dotenv(dotenv_path=repo_env, override=False)
    if not pipeline_env.exists() and not repo_env.exists():
        load_dotenv(override=False)

    from processing.runtime import configure_numba_cache

    configure_numba_cache()

    if QUEUE_NAME in queue_names:
        from processing.embeddings.clap_singleton import get_clap_model

        # SINGLETON — warm the CLAP model once per worker process (SimpleWorker runs
        # jobs in-process). Do not move this call into individual job functions.
        try:
            get_clap_model()
        except Exception as exc:  # pragma: no cover - optional dependency
            # CLAP is optional for preview/audio_features jobs; log and continue.
            print(f"CLAP warm-up skipped: {exc}")
    else:
        print(f"Queues {queue_names}: CLAP not loaded in this worker")

    if POSITION_QUEUE_NAME in queue_names:
        # Apply the idempotent positioning migration before taking jobs, while no
        # job transaction can hold locks on `tracks`.
        from jobs.position_job import ensure_positioning_schema

        ensure_positioning_schema()
        print("Positioning schema ready")

    if QUEUE_NAME in queue_names and POSITION_QUEUE_NAME in queue_names:
        print(
            "WARNING: one process consumes both CLAP and UMAP queues (torch + scikit-learn "
            "OpenMP runtimes). Fine for development; run two workers in production."
        )

    redis_conn = Redis.from_url(REDIS_URL)
    queues = [Queue(name, connection=redis_conn) for name in queue_names]
    worker = SimpleWorker(queues, connection=redis_conn)
    worker.work()


if __name__ == "__main__":
    main()
