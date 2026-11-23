"""Real-world end-to-end run through YouTube: the production path, no mocks.

POST /api/tracks/search-ingest (artist + title) -> YouTube search -> yt-dlp
download -> storage (checksum) -> audio features -> CLAP embedding (Qdrant) ->
position -> /similar.

Depends on YouTube being reachable from the machine running the workers (cloud
IPs are often challenged; set YTDLP_COOKIES_PATH). Kept out of the default and
``-m e2e`` selections:

    REBEL_E2E_API_URL=http://127.0.0.1:8000 pytest -m e2e_youtube tests/e2e -v

Run it after tests/e2e/test_pipeline_e2e.py so /similar has a catalogue to rank.
"""

from __future__ import annotations

import math
import os
import time

import pytest
import requests

pytestmark = pytest.mark.e2e_youtube

API_URL = os.getenv("REBEL_E2E_API_URL", "").rstrip("/")
JOB_TIMEOUT_SECONDS = int(os.getenv("REBEL_E2E_JOB_TIMEOUT", "900"))
ARTIST = os.getenv("REBEL_E2E_YOUTUBE_ARTIST", "Madlib")
TITLE = os.getenv("REBEL_E2E_YOUTUBE_TITLE", "Road of the Lonely Ones")

if not API_URL:
    pytest.skip("REBEL_E2E_API_URL not set: end-to-end stack not available", allow_module_level=True)


def _api(method: str, path: str, **kwargs) -> requests.Response:
    return requests.request(method, f"{API_URL}{path}", timeout=120, **kwargs)


@pytest.fixture(scope="module")
def youtube_run():
    response = _api("POST", "/api/tracks/search-ingest", json={"artist": ARTIST, "title": TITLE})
    assert response.status_code == 200, f"search-ingest failed: {response.status_code} {response.text[:500]}"
    body = response.json()

    job_ids = [str(item["job"]["id"]) for item in body["jobs"]]
    deadline = time.time() + JOB_TIMEOUT_SECONDS
    final: dict[str, dict] = {}
    while time.time() < deadline and len(final) < len(job_ids):
        for job_id in job_ids:
            if job_id not in final:
                job = _api("GET", f"/api/jobs/{job_id}").json()
                if job["status"] in {"succeeded", "failed", "cancelled"}:
                    final[job_id] = job
        time.sleep(2.0)
    assert len(final) == len(job_ids), f"jobs still running after {JOB_TIMEOUT_SECONDS}s"
    return {"ingest": body, "jobs": [final[job_id] for job_id in job_ids]}


def test_search_found_the_requested_track_on_youtube(youtube_run):
    ingest = youtube_run["ingest"]
    selected = ingest["selected_preview"]
    print(f"\nYouTube match: {selected['title']!r} ({selected['webpage_url']}, {selected.get('channel')})")
    assert ingest["provider_type"] == "youtube_music"
    assert TITLE.lower().split()[0] in selected["title"].lower()
    assert [item["type"] for item in ingest["jobs"]] == ["preview_fetch", "audio_features", "embedding", "position"]


def test_every_step_succeeded(youtube_run):
    report = [(job["job_type"], job["status"], job.get("error_message")) for job in youtube_run["jobs"]]
    for step in report:
        print(f"  {step[0]:<15} {step[1]:<10} {step[2] or ''}")
    assert all(status == "succeeded" for _, status, _ in report), report


def test_audio_was_downloaded_and_stored_with_checksum(youtube_run):
    preview = youtube_run["jobs"][0]
    metadata = preview.get("result_metadata") or {}
    assert metadata.get("storage_path"), metadata
    assert len(metadata.get("checksum") or "") == 64, metadata


def test_track_has_features_embedding_and_position(youtube_run):
    track_id = youtube_run["ingest"]["track_id"]
    detail = _api("GET", f"/api/tracks/{track_id}").json()
    assert detail.get("embedding_id"), "no CLAP embedding stored"
    assert detail.get("bpm") and 40 <= float(detail["bpm"]) <= 220
    rows = _api("GET", "/api/tracks/sonic-map", params={"limit": 5000}).json()
    row = next((r for r in rows if int(r["id"]) == int(track_id)), None)
    assert row is not None, "track missing from the sonic map"
    assert all(math.isfinite(row["position"][axis]) for axis in ("x", "y", "z"))
    print(f"  position: {row['position']} ({row['positionMethod']})")


def test_similar_returns_ranked_neighbours(youtube_run):
    track_id = youtube_run["ingest"]["track_id"]
    response = _api("GET", f"/api/tracks/{track_id}/similar", params={"limit": 5})
    assert response.status_code == 200, response.text
    results = response.json()["results"]
    assert results, "no neighbours returned"
    assert all(item["track_id"] != track_id for item in results)
    scores = [item["similarity_score"] for item in results]
    assert scores == sorted(scores, reverse=True)
    for item in results:
        print(f"  {item['similarity_score']:.3f}  {item['artist']} - {item['title']}")
