# Rebel

A 3D map visualizing musical landscapes and correlations using NodeJS, React, Three.js and Solana.

See 2-min Loom demo [https://www.loom.com/share/407133f5a33444d08a471b82696b3ed7] for a live walkthrough.

## Audio preview ingestion

1. Run the FastAPI pipeline (`python -m uvicorn api.main:app --reload` from `music-pipeline`).  
2. Launch the audio asset worker to cache previews locally or in S3:
   ```bash
   cd music-pipeline
   source .venv/bin/activate
   pip install rq redis yt-dlp  # install queue + YouTube resolver if not already present
   python -m processing.audio_asset_worker --continuous
   ```
   Configure storage via `.env` variables (`AUDIO_STORAGE_MODE`, `AUDIO_STORAGE_ROOT`, `AUDIO_STORAGE_S3_*`).
   Network throttling on some YouTube links can require longer HTTP timeouts—tune `AUDIO_PREVIEW_CONNECT_TIMEOUT`
   and `AUDIO_PREVIEW_DOWNLOAD_TIMEOUT` if large previews fail to cache.
   `yt-dlp` is required so the API can resolve YouTube previews when auto-searching.  
   Install `ffmpeg` (`brew install ffmpeg`) so YouTube `.m4a` previews can be transcoded before feature extraction—both workers inherit the PATH so `librosa` can call it.
3. Start the analysis queue worker (uses Redis/RQ) to pick up jobs triggered via the API:
   ```bash
   python -m jobs.worker
   ```
4. Ingest a track through `/api/tracks/ingest`; the worker resolves the external preview (Bandcamp, YouTube, etc.), stores it, and updates provenance fields in `audio_assets`. You can then enqueue downstream jobs (`preview_fetch`, `audio_features`, `embedding`, `position`) via `/api/jobs/enqueue`.
5. Prefer the streamlined endpoint `/api/tracks/search-ingest` (or the React Sonic Map UI) when you only know the artist/title. It uses `yt-dlp` to grab the best YouTube preview, upserts the track/audio asset, automatically enqueues the full job chain, and returns the job IDs so the frontend can poll sequentially.

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
2. Configure the model via environment variables (see `.env.example`): `CLAP_AMODEL` (defaults to `HTSAT-Large` to match LAION's public checkpoint), `CLAP_ENABLE_FUSION`, and optionally `CLAP_CHECKPOINT_PATH` if you have a local `.pt` file; if the path is missing, the worker will download the official weights automatically. `EMBEDDING_SAMPLE_RATE` defaults to 48kHz.
3. Ensure Qdrant is reachable if you want vectors pushed to the `music_embeddings` collection; set `QDRANT_HOST/PORT/API_KEY`.
4. Configure longer RQ timeouts if your first CLAP download takes a while (see `JOB_TIMEOUT_DEFAULT` / `EMBEDDING_JOB_TIMEOUT` in `.env.example`—embedding defaults to 900 s). This prevents slow checkpoints from timing out mid-transfer.
5. Start the RQ worker with `python -m jobs.worker`. Whenever an `embedding` job runs it loads the cached preview, runs CLAP, updates `tracks.embedding_id`, records metadata in `embeddings`, and upserts the vector in Qdrant.

If Qdrant or laion-clap aren't installed, the worker logs a warning but the rest of the pipeline continues.
