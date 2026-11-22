"""Real end-to-end run of the analysis pipeline. No mocks.

Requires a running stack: PostgreSQL, Redis, Qdrant, the FastAPI app and the
two RQ workers (``--queues analysis`` and ``--queues positioning``). Audio is
generated locally and served from 127.0.0.1, so no external network is used.

    REBEL_E2E_API_URL=http://127.0.0.1:8000 pytest -m e2e tests/e2e -v

Path covered for every track:
    POST /api/tracks/ingest -> preview_fetch -> audio_features -> CLAP embedding
    (Qdrant) -> position (UMAP / kNN / fallback) -> /similar, /sonic-map, /version
"""

from __future__ import annotations

import functools
import http.server
import math
import os
import socketserver
import threading
import time
import uuid
from pathlib import Path

import numpy as np
import pytest
import requests
import soundfile as sf

pytestmark = pytest.mark.e2e

API_URL = os.getenv("REBEL_E2E_API_URL", "").rstrip("/")
JOB_TIMEOUT_SECONDS = int(os.getenv("REBEL_E2E_JOB_TIMEOUT", "900"))
SAMPLE_RATE = 44100
STEPS = ("preview_fetch", "audio_features", "embedding", "position")
VALID_METHODS = {"clap_umap_full", "clap_knn_approx", "features_fallback"}
# CI lowers UMAP_MIN_TRUSTWORTHINESS on the test stack so a 12-track map can be
# published and the publication path is exercised; set this flag there.
EXPECT_PUBLISHED_MAP = os.getenv("REBEL_E2E_EXPECT_PUBLISHED_MAP", "0") == "1"

if not API_URL:
    pytest.skip("REBEL_E2E_API_URL not set: end-to-end stack not available", allow_module_level=True)


# ---------------------------------------------------------------------------
# Fixture audio: 3 families x 4 variants. Variants of one family share the same
# musical content (gain / small offset / light noise), so any sane embedding
# must rank same-family tracks first.
# ---------------------------------------------------------------------------

def _family_signal(family: str, seconds: float, rng: np.random.Generator) -> np.ndarray:
    t = np.arange(int(seconds * SAMPLE_RATE)) / SAMPLE_RATE
    if family == "bass_drone":
        sig = 0.6 * np.sin(2 * np.pi * 55 * t) + 0.3 * np.sin(2 * np.pi * 110 * t)
        sig *= 0.7 + 0.3 * np.sin(2 * np.pi * 0.25 * t)
    elif family == "bright_pluck":
        sig = np.zeros_like(t)
        for start in np.arange(0, seconds, 0.25):
            idx = (t >= start) & (t < start + 0.25)
            local = t[idx] - start
            freq = 1760 if int(start * 4) % 2 else 2637
            sig[idx] = np.sin(2 * np.pi * freq * local) * np.exp(-local * 18)
    elif family == "noise_beat":
        sig = 0.5 * rng.normal(size=t.shape)
        envelope = (np.mod(t, 0.5) < 0.06).astype(float)
        sig = sig * (0.15 + envelope)
        sig += 0.4 * np.sin(2 * np.pi * 60 * t) * envelope
    else:  # pragma: no cover
        raise ValueError(family)
    return sig / (np.max(np.abs(sig)) + 1e-9)


def _variant(sig: np.ndarray, variant: int, rng: np.random.Generator) -> np.ndarray:
    if variant == 1:
        sig = sig * 0.5
    elif variant == 2:
        sig = np.roll(sig, int(0.37 * SAMPLE_RATE))
    elif variant == 3:
        sig = sig + 0.01 * rng.normal(size=sig.shape)
    return np.clip(0.8 * sig, -1, 1).astype(np.float32)


@pytest.fixture(scope="module")
def audio_server(tmp_path_factory):
    folder = tmp_path_factory.mktemp("e2e-audio")
    rng = np.random.default_rng(42)
    files = []
    for family in ("bass_drone", "bright_pluck", "noise_beat"):
        base = _family_signal(family, 20.0, rng)
        for variant in range(4):
            name = f"{family}_{variant}.wav"
            sf.write(folder / name, _variant(base, variant, rng), SAMPLE_RATE, subtype="PCM_24")
            files.append((family, variant, name))

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(folder))
    handler.log_message = lambda *args, **kwargs: None  # type: ignore[assignment]
    socketserver.TCPServer.allow_reuse_address = True
    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    yield base_url, files
    server.shutdown()


def _api(method: str, path: str, **kwargs) -> requests.Response:
    return requests.request(method, f"{API_URL}{path}", timeout=60, **kwargs)


def _wait_for_jobs(job_ids: list[str]) -> dict[str, dict]:
    deadline = time.time() + JOB_TIMEOUT_SECONDS
    final: dict[str, dict] = {}
    while time.time() < deadline and len(final) < len(job_ids):
        for job_id in job_ids:
            if job_id in final:
                continue
            job = _api("GET", f"/api/jobs/{job_id}").json()
            if job["status"] in {"succeeded", "failed", "cancelled"}:
                final[job_id] = job
        time.sleep(1.0)
    missing = [job_id for job_id in job_ids if job_id not in final]
    assert not missing, f"jobs still running after {JOB_TIMEOUT_SECONDS}s: {missing}"
    return final


@pytest.fixture(scope="module")
def pipeline_run(audio_server):
    base_url, files = audio_server
    run_id = uuid.uuid4().hex[:8]
    tracks = {}
    for family, variant, name in files:
        response = _api(
            "POST",
            "/api/tracks/ingest",
            json={
                "mongo_track_id": f"e2e-{run_id}-{family}-{variant}",
                "title": f"e2e {family} {variant}",
                "artist": f"e2e-{run_id}",
                "genre": family,
                "audio_url": f"{base_url}/{name}",
                "preview_provider_type": "other",
                "preview_rights_scope": "analysis_only",
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()
        tracks[body["track_id"]] = {"family": family, "variant": variant, "asset": body["audio_asset_id"]}

    job_ids = []
    for track_id, info in tracks.items():
        previous = None
        for step in STEPS:
            payload = {"job_type": step, "requested_by": f"e2e-{run_id}"}
            if step in {"preview_fetch", "audio_features", "embedding"}:
                payload["audio_asset_id"] = info["asset"]
                payload["provider_type"] = "other"
            if step != "preview_fetch":
                payload["track_id"] = track_id
            params = {"depends_on": previous} if previous else None
            response = _api("POST", "/api/jobs/enqueue", json=payload, params=params)
            assert response.status_code == 200, response.text
            body = response.json()
            previous = body["queue_job_id"]
            job_ids.append(str(body["job"]["id"]))

    results = _wait_for_jobs(job_ids)
    return {"tracks": tracks, "jobs": results}


def test_every_job_succeeded(pipeline_run):
    failed = {job_id: job.get("error_message") for job_id, job in pipeline_run["jobs"].items() if job["status"] != "succeeded"}
    assert not failed, failed


def test_tracks_have_audio_features_and_clap_embeddings(pipeline_run):
    for track_id in pipeline_run["tracks"]:
        detail = _api("GET", f"/api/tracks/{track_id}").json()
        assert detail.get("embedding_id"), f"track {track_id} has no embedding"
        assert detail.get("bpm") is not None and detail.get("energy") is not None


def test_similarity_ranks_same_family_first(pipeline_run):
    tracks = pipeline_run["tracks"]
    misses = []
    for track_id, info in tracks.items():
        response = _api("GET", f"/api/tracks/{track_id}/similar", params={"limit": 3})
        assert response.status_code == 200, response.text
        body = response.json()
        results = body["results"]
        assert body["metric"] == "cosine" and body["vector_dimensions"] == 512
        assert all(item["track_id"] != track_id for item in results), "a track is its own neighbour"
        scores = [item["similarity_score"] for item in results]
        assert scores == sorted(scores, reverse=True)
        ours = [item for item in results if item["track_id"] in tracks]
        assert ours, f"no e2e neighbour returned for {track_id}"
        if tracks[ours[0]["track_id"]]["family"] != info["family"]:
            misses.append((track_id, info["family"], tracks[ours[0]["track_id"]]["family"]))
    assert not misses, f"top-1 neighbour from another family: {misses}"


def test_sonic_map_exposes_finite_positions_with_provenance(pipeline_run):
    rows = _api("GET", "/api/tracks/sonic-map", params={"limit": 5000}).json()
    by_id = {int(row["id"]): row for row in rows}
    for track_id in pipeline_run["tracks"]:
        row = by_id.get(int(track_id))
        assert row is not None, f"track {track_id} missing from sonic map"
        coords = [row["position"][axis] for axis in ("x", "y", "z")]
        assert all(value is not None and math.isfinite(value) for value in coords)
        assert row["positionMethod"] in VALID_METHODS, row["positionMethod"]


def test_map_version_endpoint_is_consistent(pipeline_run):
    response = _api("GET", "/api/sonic-map/version")
    rows = _api("GET", "/api/tracks/sonic-map", params={"limit": 5000}).json()
    full_rows = [row for row in rows if row["positionMethod"] == "clap_umap_full"]
    if response.status_code == 404:
        assert not EXPECT_PUBLISHED_MAP, "expected a published CLAP/UMAP map (REBEL_E2E_EXPECT_PUBLISHED_MAP=1)"
        assert not full_rows, "tracks claim a full UMAP position but no map version is published"
        return
    assert response.status_code == 200, response.text
    version = response.json()
    assert version["status"] == "published"
    assert version["model_name"] and version["vector_dimensions"] == 512
    for row in full_rows:
        assert row["positionVersionId"] == version["id"]
    if EXPECT_PUBLISHED_MAP:
        ours = {int(track_id) for track_id in pipeline_run["tracks"]}
        assert any(int(row["id"]) in ours for row in full_rows), "no e2e track placed by the published CLAP/UMAP map"
