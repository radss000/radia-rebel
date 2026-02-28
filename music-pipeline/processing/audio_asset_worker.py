#!/usr/bin/env python3
"""Audio asset worker.

This worker polls the ``audio_assets`` table for pending previews, resolves the
actual download URL through provider adapters, stores the preview in the
configured storage backend, and updates provenance metadata (checksum,
timestamps, fetch status).
"""

from __future__ import annotations

import argparse
import logging
import os
import time

import psycopg2

from database.utils import DB_CONFIG
from processing.audio_assets.service import (
    StorageClient,
    fetch_pending_assets,
    process_audio_asset,
    FETCH_LIMIT,
    MAX_ATTEMPTS,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("audio_asset_worker")

POLL_INTERVAL = int(os.getenv("AUDIO_ASSET_POLL_INTERVAL", 30))


def main() -> None:
    parser = argparse.ArgumentParser(description="Audio preview storage worker")
    parser.add_argument("--continuous", action="store_true", help="Run continuously with polling")
    args = parser.parse_args()

    storage = StorageClient()
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False

    try:
        while True:
            assets = fetch_pending_assets(conn)
            if not assets:
                if not args.continuous:
                    logger.info("No pending assets. Exiting.")
                    break
                logger.debug("No pending assets. Sleeping %ss", POLL_INTERVAL)
                time.sleep(POLL_INTERVAL)
                continue

            for asset in assets:
                try:
                    process_audio_asset(conn, asset["id"], storage=storage, commit=True)
                except Exception:
                    # process_audio_asset already logs and updates state; failure is swallowed to continue loop
                    pass

            if not args.continuous:
                break
    finally:
        conn.close()


if __name__ == "__main__":
    main()
