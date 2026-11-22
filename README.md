# Rebel

A 3D map visualizing musical landscapes and correlations using Node.js, React, native WebGL and Solana.

See 2-min Loom demo [https://www.loom.com/share/407133f5a33444d08a471b82696b3ed7] for a live walkthrough.

## Audio preview ingestion

1. Run the FastAPI pipeline (`python -m uvicorn api.main:app --reload` from `music-pipeline`).  
2. Launch the audio asset worker to cache previews locally or in GCS:
   ```bash
   cd music-pipeline
   source .venv/bin/activate
   pip install -r requirements.txt
   python -m processing.audio_asset_worker --continuous
   ```
   Configure storage via `.env` variables (`AUDIO_STORAGE_MODE`, `AUDIO_STORAGE_ROOT`, `GCS_BUCKET`, `GCP_CREDENTIALS_PATH`).
   Network throttling on some YouTube links can require longer HTTP timeouts—tune `AUDIO_PREVIEW_CONNECT_TIMEOUT`
   and `AUDIO_PREVIEW_DOWNLOAD_TIMEOUT` if large previews fail to cache.
   Install `ffmpeg` (`brew install ffmpeg`) so YouTube `.m4a` previews can be transcoded before feature extraction—both workers inherit the PATH so `librosa` can call it.
3. Start the queue workers (Redis/RQ). Production runs two processes so torch/CLAP and UMAP/scikit-learn
   (two incompatible OpenMP runtimes) never share one:
   ```bash
   python -m jobs.worker --queues analysis      # preview_fetch, audio_features, embedding (loads CLAP)
   python -m jobs.worker --queues positioning   # position (UMAP), applies the positioning migration at startup
   ```
   `python -m jobs.worker` alone consumes both queues in one process (development only). Steps of one track are
   chained with RQ `depends_on`, and a failed step marks the remaining steps of that track as failed.
4. Ingest a track through `/api/tracks/ingest`; the worker resolves the external preview (Bandcamp, YouTube, etc.), stores it, and updates provenance fields in `audio_assets`. You can then enqueue downstream jobs (`preview_fetch`, `audio_features`, `embedding`, `position`) via `/api/jobs/enqueue`.
5. Prefer the streamlined endpoint `/api/tracks/search-ingest` (or the React Sonic Map UI) when you only know the artist/title. It scrapes YouTube's public search results to pick the best match, upserts the track/audio asset, automatically enqueues the full job chain, and returns the job IDs so the frontend can poll sequentially.

The Sonic Map admin page (`frontend/src/pages/SonicMapPage.js`) exposes a “Search & analyze a new track” form that calls `/api/tracks/search-ingest`, streams each job step, and refreshes the native React/WebGL universe as soon as the `position` job finishes. The renderer has no runtime CDN dependency: once the application and map data are loaded, orbiting, zooming, filtering and point selection do not require an internet connection.

### End-to-end test (real stack, no mocks)

`music-pipeline/tests/e2e/` ingests 12 generated tracks served from `127.0.0.1`, runs every job through the real
workers (PostgreSQL, Redis, Qdrant >= 1.10, CLAP) and checks `/similar`, `/api/tracks/sonic-map` and
`/api/sonic-map/version`. It runs in GitHub Actions (`.github/workflows/music-pipeline.yml`) and locally with:

```bash
docker compose up -d postgres redis qdrant
cd music-pipeline && bash scripts/run_e2e_local.sh   # uses a throwaway rebel_e2e database
```

Existing databases must apply `music-pipeline/database/migrations/20261122_embeddings_track_unique.sql`
(embedding jobs fail without the unique index on `embeddings.track_id`).

### Backfilling existing catalogue entries

If you already have tracks with cached previews (or after importing metadata through the crawler), run:

```bash
cd music-pipeline
python processing/calculate_audio_features.py --limit 200
```

The CLI inspects the `tracks` + `audio_assets` tables, determines which jobs are still missing
(`preview_fetch`, `audio_features`, `embedding`, `position`), and enqueues them through the same Redis/RQ queue so the workers you launched in step 3 can process them. Use `--dry-run` to audit actions without enqueuing, or `--steps audio_features,position` to restrict to specific jobs.

### Audio embeddings (CLAP)

The `embedding` job now generates real vectors from the cached preview using LAION-CLAP:

1. Install PyTorch, torchaudio, torchvision, and laion-clap (already listed in `music-pipeline/requirements.txt`). On Apple Silicon:
   ```bash
   pip install torch==2.2.2 torchaudio==2.2.2 --extra-index-url https://download.pytorch.org/whl/cpu
   pip install laion-clap==1.1.4
   ```
2. Configure the model via environment variables (see `.env.example`). Use the music-specialized checkpoint by setting `CLAP_CHECKPOINT_PATH=checkpoints/music_audioset_epoch_15_esc_90.14.pt`, `CLAP_AMODEL=HTSAT-base`, `CLAP_ENABLE_FUSION=false`, and `EMBEDDING_SAMPLE_RATE=48000`. If you want another architecture, point `CLAP_CHECKPOINT_PATH` at the compatible `.pt` file to prevent shape mismatches.
3. (macOS) If MPS runs out of memory, set `CLAP_DEVICE=cpu` to force CPU inference for stability.
3. Ensure Qdrant is reachable if you want vectors pushed to the `music_embeddings` collection; set `QDRANT_HOST/PORT/API_KEY`.
4. Configure longer RQ timeouts if your first CLAP download takes a while (see `JOB_TIMEOUT_DEFAULT` / `EMBEDDING_JOB_TIMEOUT` in `.env.example`—embedding defaults to 900 s). This prevents slow checkpoints from timing out mid-transfer.
5. Start the RQ workers as described above (`--queues analysis` and `--queues positioning`). The analysis worker warms a singleton CLAP model at startup, so all embedding jobs reuse the same instance. Whenever an `embedding` job runs it loads the cached preview, runs CLAP, updates `tracks.embedding_id`, records metadata in `embeddings`, and upserts the vector in Qdrant.

The worker keeps Numba JIT enabled for UMAP performance and configures a writable cache under the system temporary directory. Set `NUMBA_CACHE_DIR` only when the deployment requires a persistent custom cache path; do not set `NUMBA_DISABLE_JIT`, because it makes full map recalculation impractically slow.

If Qdrant or laion-clap aren't installed, the worker logs a warning but the rest of the pipeline continues.

### CLAP similarity API

Once a track has an embedding in Qdrant, request its nearest compatible neighbors with:

```bash
curl "http://localhost:8000/api/tracks/42/similar?limit=10&offset=0&min_score=0"
```

The endpoint ranks results by cosine similarity in the original CLAP vector space, excludes the source track, and only returns embeddings with the same model name, model version, and vector dimensions. The response also includes the secondary 3D distance and `position_method`, but those fields are not used for ranking.

Similarity bands remain `null` until calibrated thresholds are configured through `SIMILARITY_VERY_CLOSE_THRESHOLD`, `SIMILARITY_CLOSE_THRESHOLD`, and `SIMILARITY_RELATED_THRESHOLD`. Keep these variables unset until they have been measured against the REBEL validation corpus.

### Versioned Sonic Map positioning

The position job publishes full CLAP/UMAP maps atomically. Coordinates are written to a staging table, checked against `UMAP_MIN_TRUSTWORTHINESS` and `UMAP_MIN_NEIGHBOR_RECALL`, aligned to existing full-map anchors, and only then promoted as the single published map version. Failed quality checks are recorded as rejected versions and never replace the active map.

The neighbor-recall gate defaults provisionally to `0.35`: a 1,000-track structured synthetic benchmark reached `0.456` recall with `0.987` trustworthiness. The stricter `0.70` product target remains part of phase-4 corpus calibration because exact top-10 recall penalizes interchangeable near-neighbors inside dense musical clusters.

Incremental tracks use `clap_knn_approx` only when enough finite, positive-similarity CLAP neighbors already have valid positions. Audio-feature fallback positions use `features_fallback` and are never treated as CLAP neighbors. Retrieve the active map provenance with `GET /api/sonic-map/version`; each Sonic Map track also exposes `positionMethod`, `positionVersionId`, `positionedAt`, and `positionQuality`.

### React/WebGL Sonic Universe

The maintained 3D experience lives in `frontend/src/components/sonic-map/SonicUniverse.js`. It renders the versioned coordinates with native WebGL, filters tracks by positioning provenance, exposes map trustworthiness/neighbor recall, and highlights exact neighbors returned by the CLAP similarity endpoint. The 3D distance remains exploratory; displayed ADN percentages come from cosine similarity in the original CLAP embedding space.

The browser loads map data through the same-origin Node proxy (`GET /api/tracks/sonic-map?limit=...`) rather than directly calling the Python port. If WebGL is unavailable, the component provides an accessible selectable list instead of failing silently.

Existing databases can apply `music-pipeline/database/migrations/20260808_positioning_v1.sql`. The position worker also applies this idempotent migration before its first positioning job.

### YouTube preview fetching

The preview worker now uses `yt-dlp` to download YouTube audio previews directly, then hands those bytes to the storage backend.

1. Install `yt-dlp` (pinned in `music-pipeline/requirements.txt`) and ensure ffmpeg is available if you want consistent audio formats or preview trimming.
2. Adjust `YTDLP_FORMAT` and `YTDLP_AUDIO_FORMAT` to control the download flavor. If you set `COBALT_PREVIEW_DURATION_SECONDS` (>0, clamped 30–60 s) the worker trims with ffmpeg before passing bytes to `processing.audio_assets.service.StorageClient`, so previews land as uniform snippets regardless of storage backend (`local`, `s3`, or `gcs`).
3. If extraction fails, try pinning YouTube player clients with `YTDLP_PLAYER_CLIENTS` (defaults to `android`). For 403s, provide cookies via `YTDLP_COOKIES_PATH` (recommended for production) or `YTDLP_COOKIES_FROM_BROWSER`, or set `YTDLP_REFERER`/`YTDLP_ORIGIN`. You can also tune `YTDLP_PROXY`, `YTDLP_USER_AGENT`, or `YTDLP_IMPERSONATE`.
4. To generate a reusable cookies file, run:
   ```bash
   ./music-pipeline/venv/bin/python -m processing.youtube.cookies_refresh --browser chrome --output music-pipeline/secrets/youtube_cookies.txt
   ```
   Then set `YTDLP_COOKIES_PATH` and refresh that file on a schedule (cron/systemd timer) on a workstation or headless login host.
4. The FastAPI `/api/tracks/search-ingest` endpoint still performs a lightweight scrape of YouTube's public search page (no OAuth required) to find the first playable result when no manual URL is provided. Set `YOUTUBE_SEARCH_USER_AGENT`, `YOUTUBE_SEARCH_ACCEPT_LANGUAGE`, and `YOUTUBE_SEARCH_TIMEOUT` if you need to tune that scraper for your region.
