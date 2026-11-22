-- embedding_task upserts with ON CONFLICT (track_id), which requires a unique
-- index on embeddings.track_id. Databases created from schema.sql before this
-- migration only had a plain index, so every embedding job failed with
-- "there is no unique or exclusion constraint matching the ON CONFLICT specification".
-- Idempotent: keeps the most recent row per track, then adds the unique index.
BEGIN;

DELETE FROM embeddings e
USING embeddings newer
WHERE e.track_id = newer.track_id
  AND (newer.created_at, newer.id::text) > (e.created_at, e.id::text);

CREATE UNIQUE INDEX IF NOT EXISTS idx_embeddings_track_unique ON embeddings(track_id);

COMMIT;
