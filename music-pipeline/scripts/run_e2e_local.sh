#!/usr/bin/env bash
# Real end-to-end run on your machine (same steps as the CI "e2e" job).
# Uses a throwaway database "rebel_e2e" and Qdrant collection "music_embeddings_e2e"
# so your dev data is not touched. Requires: docker compose services up
# (postgres, redis, qdrant >= 1.10), the venv with requirements, and the CLAP checkpoint.
#
#   cd music-pipeline && bash scripts/run_e2e_local.sh
set -euo pipefail
cd "$(dirname "$0")/.."

export POSTGRES_DB=rebel_e2e
export QDRANT_COLLECTION=music_embeddings_e2e
export ANALYSIS_QUEUE_NAME=analysis_e2e
export POSITION_QUEUE_NAME=positioning_e2e
export AUDIO_STORAGE_MODE=local
export UMAP_MIN_TRUSTWORTHINESS=0.5
export REBEL_E2E_API_URL=http://127.0.0.1:8765
export REBEL_E2E_EXPECT_PUBLISHED_MAP=1
LOG_DIR="$(mktemp -d)"

echo "Logs: $LOG_DIR"
psql -h "${POSTGRES_HOST:-localhost}" -U "${POSTGRES_USER:-rebel}" -d postgres -q \
  -c "DROP DATABASE IF EXISTS rebel_e2e WITH (FORCE)" || true
curl -s -X DELETE "http://${QDRANT_HOST:-localhost}:${QDRANT_PORT:-6333}/collections/${QDRANT_COLLECTION}" > /dev/null || true
python database/init_db.py > "$LOG_DIR/init.log" 2>&1

python -m uvicorn api.main:app --host 127.0.0.1 --port 8765 > "$LOG_DIR/api.log" 2>&1 &
PIDS=($!)
python -m jobs.worker --queues "$ANALYSIS_QUEUE_NAME" > "$LOG_DIR/worker-analysis.log" 2>&1 &
PIDS+=($!)
python -m jobs.worker --queues "$POSITION_QUEUE_NAME" > "$LOG_DIR/worker-positioning.log" 2>&1 &
PIDS+=($!)
trap 'kill "${PIDS[@]}" 2>/dev/null || true' EXIT

echo "Waiting for the API and for CLAP to load in the analysis worker..."
until curl -sf "$REBEL_E2E_API_URL/" > /dev/null; do sleep 2; done
until grep -q "Listening on $ANALYSIS_QUEUE_NAME" "$LOG_DIR/worker-analysis.log"; do sleep 5; done

python -m pytest -m e2e tests/e2e -v
