# Rebel

A 3D map visualizing musical landscapes and correlations using NodeJS, React, Three.js and Solana.

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
3. Start the analysis queue worker (uses Redis/RQ) to pick up jobs triggered via the API:
   ```bash
   python -m jobs.worker
   ```
4. Ingest a track through `/api/tracks/ingest`; the worker resolves the external preview (Bandcamp, YouTube, etc.), stores it, and updates provenance fields in `audio_assets`. You can then enqueue downstream jobs (`preview_fetch`, `audio_features`, `embedding`, `position`) via `/api/jobs/enqueue`.
5. Prefer the streamlined endpoint `/api/tracks/search-ingest` (or the React Sonic Map UI) when you only know the artist/title. It scrapes YouTube's public search results to pick the best match, upserts the track/audio asset, automatically enqueues the full job chain, and returns the job IDs so the frontend can poll sequentially.

The Sonic Map admin page (`frontend/src/pages/SonicMapPage.js`) now exposes a “Search & analyze a new track” form that calls `/api/tracks/search-ingest`, streams the progress of each job step, and refreshes the Babylon map as soon as the `position` job finishes.

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
2. Configure the model via environment variables (see `.env.example`). The worker defaults to the bundled `HTSAT-tiny` weights published with laion-clap; set `CLAP_AMODEL=HTSAT-tiny` (default) unless you have downloaded a matching checkpoint locally. If you want `HTSAT-large` or another architecture, point `CLAP_CHECKPOINT_PATH` at the compatible `.pt` file to prevent shape mismatches. `CLAP_ENABLE_FUSION` toggles the fusion variant, and `EMBEDDING_SAMPLE_RATE` defaults to 48 kHz.
3. Ensure Qdrant is reachable if you want vectors pushed to the `music_embeddings` collection; set `QDRANT_HOST/PORT/API_KEY`.
4. Configure longer RQ timeouts if your first CLAP download takes a while (see `JOB_TIMEOUT_DEFAULT` / `EMBEDDING_JOB_TIMEOUT` in `.env.example`—embedding defaults to 900 s). This prevents slow checkpoints from timing out mid-transfer.
5. Start the RQ worker with `python -m jobs.worker`. Whenever an `embedding` job runs it loads the cached preview, runs CLAP, updates `tracks.embedding_id`, records metadata in `embeddings`, and upserts the vector in Qdrant.

If Qdrant or laion-clap aren't installed, the worker logs a warning but the rest of the pipeline continues.

### YouTube preview fetching

The preview worker now uses `yt-dlp` to download YouTube audio previews directly, then hands those bytes to the storage backend.

1. Install `yt-dlp` (pinned in `music-pipeline/requirements.txt`) and ensure ffmpeg is available if you want consistent audio formats or preview trimming.
2. Adjust `YTDLP_FORMAT` and `YTDLP_AUDIO_FORMAT` to control the download flavor. If you set `COBALT_PREVIEW_DURATION_SECONDS` (>0, clamped 30–60 s) the worker trims with ffmpeg before passing bytes to `processing.audio_assets.service.StorageClient`, so previews land as uniform snippets regardless of storage backend (`local`, `s3`, or `gcs`).
3. If extraction fails, try pinning YouTube player clients with `YTDLP_PLAYER_CLIENTS` (defaults to `android`). For 403s, provide cookies via `YTDLP_COOKIES_PATH` or `YTDLP_COOKIES_FROM_BROWSER`, or set `YTDLP_REFERER`/`YTDLP_ORIGIN`. You can also tune `YTDLP_PROXY`, `YTDLP_USER_AGENT`, or `YTDLP_IMPERSONATE`.
4. The FastAPI `/api/tracks/search-ingest` endpoint still performs a lightweight scrape of YouTube's public search page (no OAuth required) to find the first playable result when no manual URL is provided. Set `YOUTUBE_SEARCH_USER_AGENT`, `YOUTUBE_SEARCH_ACCEPT_LANGUAGE`, and `YOUTUBE_SEARCH_TIMEOUT` if you need to tune that scraper for your region.
