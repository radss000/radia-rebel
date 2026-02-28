#!/usr/bin/env python3
from __future__ import annotations

import multiprocessing

"""RQ worker for analysis jobs."""

multiprocessing.set_start_method("spawn", force=True)

import os

from redis import Redis
from rq import Queue, Worker

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
QUEUE_NAME = os.getenv("ANALYSIS_QUEUE_NAME", "analysis")


def main() -> None:
    redis_conn = Redis.from_url(REDIS_URL)
    queue = Queue(QUEUE_NAME, connection=redis_conn)
    worker = Worker([queue], connection=redis_conn)
    worker.work()


if __name__ == "__main__":
    main()
