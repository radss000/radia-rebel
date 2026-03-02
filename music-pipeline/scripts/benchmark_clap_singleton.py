import json
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Tuple

import requests

API_BASE = "http://localhost:8000"
POLL_INTERVAL_SEC = 2
TIMEOUT_SEC = 1800

TRACKS = [
    {"artist": "Underground Resistance", "title": "The Seawolf"},
    {"artist": "Jeff Mills", "title": "The Bells"},
    {"artist": "Robert Hood", "title": "Minus"},
]


def _post_json(path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    response = requests.post(f"{API_BASE}{path}", json=payload, timeout=30)
    response.raise_for_status()
    return response.json()


def _get_json(path: str) -> Dict[str, Any]:
    response = requests.get(f"{API_BASE}{path}", timeout=30)
    response.raise_for_status()
    return response.json()


def _wait_for_job(job_id: str) -> Dict[str, Any]:
    start = time.time()
    while True:
        job = _get_json(f"/api/jobs/{job_id}")
        status = job.get("status")
        if status in {"succeeded", "failed"}:
            return job
        if time.time() - start > TIMEOUT_SEC:
            raise TimeoutError(f"Timeout waiting for job {job_id}")
        time.sleep(POLL_INTERVAL_SEC)


def _parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _duration_ms(job: Dict[str, Any]) -> int:
    started = job.get("started_at")
    completed = job.get("completed_at")
    if not started or not completed:
        raise ValueError("Missing started_at/completed_at for job timing")
    start_dt = _parse_dt(started)
    end_dt = _parse_dt(completed)
    return int((end_dt - start_dt).total_seconds() * 1000)


def main() -> int:
    print("Enqueueing 3 search-ingest jobs...")
    embedding_jobs: List[Tuple[str, str]] = []

    for index, track in enumerate(TRACKS, start=1):
        payload = {
            "artist": track["artist"],
            "title": track["title"],
        }
        result = _post_json("/api/tracks/search-ingest", payload)
        jobs = result.get("jobs", [])
        embedding_job = next((j for j in jobs if j.get("type") == "embedding"), None)
        if not embedding_job:
            raise RuntimeError(f"No embedding job returned for track {payload}")
        embedding_jobs.append((f"Job {index}", embedding_job["job"]["id"]))
        print(f"Queued {payload['artist']} - {payload['title']}: {embedding_job['job']['id']}")

    print("Waiting for embedding jobs to complete...")
    durations = []
    for label, job_id in embedding_jobs:
        job = _wait_for_job(job_id)
        if job.get("status") != "succeeded":
            raise RuntimeError(
                f"{label} failed: {job.get('error_message') or json.dumps(job, indent=2)}"
            )
        duration = _duration_ms(job)
        durations.append(duration)
        print(f"{label} completed in {duration}ms")

    if len(durations) < 3:
        raise RuntimeError("Expected 3 embedding jobs to benchmark")

    t1, t2, t3 = durations
    ratio = t1 / max(t2, 1)
    print(f"Job 1: {t1}ms | Job 2: {t2}ms | Job 3: {t3}ms | ratio: {ratio:.1f}x")
    return 0


if __name__ == "__main__":
    sys.exit(main())
