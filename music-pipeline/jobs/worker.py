#!/usr/bin/env python3
from __future__ import annotations

import multiprocessing

"""RQ worker for analysis jobs."""

multiprocessing.set_start_method("spawn", force=True)

import os
from pathlib import Path

from dotenv import load_dotenv
from redis import Redis
from rq import Queue, Worker
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
QUEUE_NAME = os.getenv("ANALYSIS_QUEUE_NAME", "analysis")


def main() -> None:
    pipeline_root = Path(__file__).resolve().parents[1]
    pipeline_env = pipeline_root / ".env"
    repo_env = pipeline_root.parent / ".env"
    if pipeline_env.exists():
        load_dotenv(dotenv_path=pipeline_env, override=False)
    if repo_env.exists():
        load_dotenv(dotenv_path=repo_env, override=False)
    if not pipeline_env.exists() and not repo_env.exists():
        load_dotenv(override=False)

    from processing.embeddings.clap_singleton import get_clap_model

    # SINGLETON — warm the CLAP model in the worker parent process so forked jobs reuse it.
    # Do not move this call into individual job functions.
    try:
        get_clap_model()
    except Exception as exc:  # pragma: no cover - optional dependency
        # CLAP is optional for preview/audio_features jobs; log and continue.
        print(f"CLAP warm-up skipped: {exc}")

    redis_conn = Redis.from_url(REDIS_URL)
    queue = Queue(QUEUE_NAME, connection=redis_conn)
    worker = Worker([queue], connection=redis_conn)
    worker.work()


if __name__ == "__main__":
    main()
