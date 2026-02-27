## 2025-11-21 · YouTube previews back on yt-dlp

- Replaced the cobalt-backed YouTube preview adapter with a yt-dlp download path that returns local audio files to the preview worker.
- Updated docs/env examples with yt-dlp tuning options while retaining `COBALT_PREVIEW_DURATION_SECONDS` for preview trimming.
- Documented optional yt-dlp tuning (cookies/proxy/user-agent/impersonation) for more reliable YouTube downloads.

## 2025-11-20 · Cobalt-backed YouTube previews

- Replaced the OAuth-based YouTube adapter with a cobalt API resolver that streams tunnel URLs straight into `processing.audio_assets.service` while keeping the storage client untouched.
- Removed every Google OAuth dependency: deleted `processing/google/*` + `processing/youtube/*`, dropped the `google_oauth_tokens` table from both schema files, and trimmed `google-auth*` from `requirements.txt`.
- Added cobalt/search configuration knobs (`COBALT_*`, `YOUTUBE_SEARCH_*`) to `.env` + `.env.example`, rewrote the README setup section, and documented the new scraping-based `/api/tracks/search-ingest` behaviour.
- Defaulted cobalt traffic to the local docker instance (`http://127.0.0.1:9000/`) with API key support baked into `.env`, preventing accidental calls to the hosted `api.cobalt.tools`.
- Audio preview worker now clamps every cobalt download to `COBALT_PREVIEW_DURATION_SECONDS` (30‑60 s, ffmpeg-backed) before calling `StorageClient`, keeping preview lengths uniform regardless of provider.
- Implemented a lightweight YouTube search scraper inside `api/main.py` so track ingest works without the Data API, and updated the changelog/docs to reflect the cobalt flow replacing the yt-dlp/PO-token stack entirely.

## 2025-11-16 · Google OAuth previews & GCS storage

- Swapped the yt-dlp/PO-token flow for a native Google OAuth integration: new table `google_oauth_tokens`, CLI (`python -m processing.youtube.oauth_cli login`) to seed refresh tokens, and a YouTube preview adapter that hits the official youtubei player endpoint with OAuth access tokens.
- Removed the entire yt-dlp dependency stack (`processing.youtube.token_*`, cookie jars, PO token refresher) and updated FastAPI search to use the YouTube Data API instead of yt-dlp scrapes.
- Extended `StorageClient` with a GCS backend so preview bytes are uploaded to `gs://…` via `google-cloud-storage` when `AUDIO_STORAGE_MODE=gcs` is set.
- Cleaned up `.env.example`, README, and docs to reflect the new OAuth/GCS flow and dropped all references to cookies or yt-dlp tuning.

## 2025-11-13 · YouTube preview segmenter

- Added a `yt-dlp`-backed download path inside `processing.providers.youtube.YouTubePreviewAdapter` that trims previews to a configurable 30‑60 s window, stores them as local temp files, and bypasses the brittle PO-token-only workflow for public videos.
- Extended `PreviewFetchResult`/`processing.audio_assets.service` so adapters can return local files instead of remote URLs; the worker now hashes + stores those bytes directly and cleans up the temp media afterwards.
- Introduced env knobs (`YOUTUBE_PREVIEW_MODE`, duration/start seconds, temp dir, optional cookies/proxy) in `.env.example` so ops can tune segment length or re-enable the legacy streaming fallback if needed.

## 2025-11-12 · YouTube preview reliability

- Added `processing.youtube.token_store` and refactored the YouTube adapter so workers read the latest Android PO token from a shared JSON cache or env override, enabling zero-downtime token swaps.
- Introduced `processing.youtube.token_refresher` (CLI/daemon) that uses Rebel’s authenticated cookies + yt-dlp to mint fresh PO tokens on a schedule, persisting them with timestamps/expiry metadata and locked-down file permissions.
- Extended `.env.example`, README, and a new ops doc (`docs/youtube-preview-reliability.md`) with the full automation blueprint: cookie vault, refresher deployment, worker integration, scaling guidance, and monitoring hooks.
- Audio preview downloads now emit structured `preview_download_failed` log entries (with provider, host, HTTP status) so expiring YouTube credentials trigger alerts before the queue backs up.

## 2025-11-10 · Real CLAP embeddings in job pipeline

- Swapped the placeholder embedding task for a real LAION-CLAP inference path that loads cached previews at 48kHz, stores metadata in Postgres, and syncs vectors to Qdrant when available.
- Added reusable audio-loading helpers so both feature extraction and embedding generation share the same ffmpeg fallback/mono resampling logic.
- Ensured both the FastAPI ingest endpoint and the backfill CLI pass `audio_asset_id` into embedding jobs, guaranteeing the worker can locate the stored preview.
- Documented the new CLAP/Qdrant configuration knobs, added torch/torchaudio/laion-clap to `requirements.txt`, and expanded `.env.example`/README with setup instructions.
- Added job timeout controls (`JOB_TIMEOUT_DEFAULT`, `EMBEDDING_JOB_TIMEOUT`) so slower CLAP downloads don’t hit the RQ 180 s cap; embedding jobs now default to a 900 s timeout via `jobs/queue.py`.
- CLAP checkpoint path is now optional: if `CLAP_CHECKPOINT_PATH` is unset or points to a missing file, the worker downloads the official weights automatically. `.env.example` defaults to `HTSAT-Large` to match the published checkpoint.
- Automatically load `.env` via `python-dotenv` and default `CLAP_AMODEL` to `HTSAT-large`, so workers started from `music-pipeline/` pick up the correct model without manual exports.

## 2025-11-07 · Unified analysis jobs & backfill CLI

- Removed the legacy genre-based `processing/embeddings_generator.py` + synthetic feature calculator and replaced them with a single backfill CLI (`processing/calculate_audio_features.py`) that inspects audio assets and enqueues the real `preview_fetch → audio_features → embedding → position` jobs.
- Introduced `jobs.queue` so both the FastAPI endpoints and command-line tools share the same logic for inserting/enqueuing `analysis_jobs`, preventing diverging code paths between realtime ingest and batch backfills.
- Updated `music-pipeline/api/main.py` and `database/init_db.py` to reference the shared queue helpers, simplifying deployment steps and keeping every backend entry point on the task queue architecture.
- Documented the new CLI usage in `README.md`, including dry-run support and selective job steps, so no one reruns the synthetic calculators by mistake.

## 2025-11-06 · Sonic Map auto-ingest workflow

- Added a full search-ingest stack in `music-pipeline/api/main.py`: YouTube lookup via `yt-dlp`, track/audio-asset upsert helper, and the `/api/tracks/search-ingest` endpoint that enqueues the entire `preview_fetch → audio_features → embedding → position` chain and returns every job id for polling.
- Reset audio asset provenance when reusing a provider id so preview downloads happen again (storage path/checksum cleared, attempts reset) and record the selected preview metadata in the API response.
- Extended the pipeline client + UI (`frontend/src/services/pipeline.js`, `frontend/src/pages/SonicMapPage.js`) with a “Search & analyze a new track” form that accepts artist/title + optional URL override, launches the backend workflow, monitors each job status sequentially, surfaces errors, and refreshes the sonic map once the final job succeeds.
- Documented the new endpoint plus the `yt-dlp` runtime dependency in `README.md` so local environments install the resolver before using the automated flow.
- Added ffmpeg-based fallback decoding inside `music-pipeline/processing/audio_features.py` so AAC `.m4a` previews from YouTube are transcoded to WAV when libsndfile/audioread cannot decode them, eliminating the “Audio feature extraction failed” errors on macOS without native AAC support. README now calls out ffmpeg as a required system dependency for the worker.

## 2025-11-02 · Audio previews & link enrichment

- Ajout d’un enrichissement multimédia dans `music-pipeline/scrapers/musicbrainz_crawler.py` : récupération Discogs (vidéos YouTube, Bandcamp), recherche Deezer (preview MP3 + lien), fallback YouTube Music via Piped, mise en cache et upsert atomique pour éviter les doublons.
- Exposition des nouvelles données via `music-pipeline/api/main.py` : chaque piste du Sonic Map renvoie désormais `preview_url` et un objet `links` (Bandcamp, YouTube, Deezer, Discogs).
- Lecture intelligente côté front (`public/sonic-map/index-new.html`) : priorisation des previews directs, intégration d’iframes YouTube/Deezer, fallback externe Bandcamp/Discogs, gestion des états play/pause et barre de progression, notifications cohérentes.
- Extension CSP dans `src/app.js` pour autoriser les embeddings audio (YouTube nocookie, widget Deezer) tout en conservant la sandbox REBEL.
- UI enrichie (`public/sonic-map/sonic-map-costar-styles.css`) : conteneur d’embed, badges de liens externes, styles désactivés quand aucun flux n’est disponible.

## 2025-11-02 · Refonte Sonic Map (agent design immersif)

- Implémentation d'une nouvelle charte sombre inspirée Co–Star pour `public/sonic-map/sonic-map-costar-styles.css` : dégradés galactiques, grille cosmique, typographies EB Garamond + IBM Plex Sans, capsules en verre dépoli et barres audio lumineuses.
- Harmonisation de l'univers 3D dans `public/sonic-map/index-new.html` : tone mapping, glow layer Babylon.js, éclairages atmosphériques, sphères réactives avec halos et outlines dynamiques.
- Amélioration de l'expérience utilisateur : cartes « Now Playing », HUD et notifications translucides, animations de focus et réinitialisation des états au close.
- Prise de rôle : gardien de l'esthétique REBEL (respect des visuels existants, immersion élégante, simplicité au service des artistes et des fans).
## 2025-11-02 · Sonic Map preview resilience

- Simplification du lecteur dans `public/sonic-map/index-new.html` : uniquement l’audio direct est lu en ligne, les sources YouTube/Deezer/Bandcamp ouvrent désormais un onglet externe avec message contextuel pour éviter les erreurs de permissions/auto-play.
- Ajout d’un placeholder UX (`preview-placeholder`) dans `public/sonic-map/sonic-map-costar-styles.css` pour informer l’utilisateur du statut du preview.
- Nettoyage des états du bouton Play/Pause et notifications afin d’éviter les iframes cassées et les warnings navigateur.

## 2025-11-03 · Audio asset provenance bootstrap

- Ajoute le schéma `audio_assets` et ses enums dans `music-pipeline/database/schema.sql` et `music-pipeline/scrapers/schema.sql`, avec trigger `trigger_set_timestamp` partagé pour tenir à jour `updated_at`.
- Enrichit l’ingestion (`music-pipeline/api/main.py`) : calcul du checksum SHA-256, normalisation provider/rights, upsert dans `audio_assets` avec suivi licence/expiry et renvoi `audio_asset_id`.
- Introduit `music-pipeline/database/models.py` pour exposer les enums et le modèle SQLAlchemy `AudioAsset`, servant de base aux jobs et migrations futurs.

## 2025-11-04 · Preview adapters & storage worker

- Implémente la couche d’adapters (`music-pipeline/processing/providers/`) avec Bandcamp (scraping data-tralbum) et un stub YouTube basé sur `yt-dlp`, registre extensible inclus.
- Ajoute le worker `processing/audio_asset_worker.py` : résout les previews via adapters, stocke localement/S3, met à jour `audio_assets` (checksum, timestamps, erreurs).
- Ajuste l’API d’ingestion (`music-pipeline/api/main.py`) pour laisser les assets en `fetch_status=pending`, nouvelle configuration `.env.example` et documentation `README.md`.
- Étend le schéma Postgres (`music-pipeline/database/schema.sql`, `music-pipeline/scrapers/schema.sql`) avec `analysis_jobs`, enums de statut/type, triggers `updated_at`, et clés étrangères bidirectionnelles avec `audio_assets`.
- Ajoute la stack jobs RQ (`music-pipeline/jobs`) : tâches `preview_fetch`, `audio_features`, `embedding`, `position` mises à jour dans `analysis_jobs`, worker Redis (`python -m jobs.worker`) et endpoints FastAPI `/api/jobs/enqueue`, `/api/jobs/{id}` proxifiés via l’API Node.
- Assure la déduplication des embeddings (`embeddings.track_id`) via un index unique pour permettre le `ON CONFLICT` du job `embedding`.
## 2025-11-05 · Sonic Map pipeline orchestration UI

- Added a dedicated pipeline client (`frontend/src/services/pipeline.js`) to call the FastAPI search, ingest, job, and sonic-map endpoints from the React app with consistent error handling.
- Rebuilt `frontend/src/pages/SonicMapPage.js` into a full workflow hub: search tracks, inspect preview metadata, trigger sequential jobs (`preview_fetch`, `audio_features`, `embedding`, `position`), poll their status, and surface retry/abort controls.
- Automatically refresh the Babylon sonic map iframe once jobs finish and expose map refresh controls (with track count + timestamp) so new embeddings/positions appear without manual reloads.
- Captured progress/error states for every job step to keep users informed while long-running processing completes.
- Loosened the Sonic Map CSP (`src/app.js`) to allow Google Fonts, normalized Deezer previews to the `other` provider bucket, and ensured ingestion payloads include a fallback `mongo_track_id` plus omit null fields (`frontend/src/pages/SonicMapPage.js`) so backend validation rules are satisfied.
