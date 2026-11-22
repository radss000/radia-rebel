CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

ALTER TABLE tracks ADD COLUMN IF NOT EXISTS position_version_id UUID;
ALTER TABLE tracks ADD COLUMN IF NOT EXISTS positioned_at TIMESTAMPTZ;
ALTER TABLE tracks ADD COLUMN IF NOT EXISTS position_quality JSONB DEFAULT '{}'::jsonb;

CREATE TABLE IF NOT EXISTS sonic_map_versions (
    id UUID PRIMARY KEY,
    status VARCHAR(20) NOT NULL CHECK (status IN ('staging', 'published', 'rejected', 'superseded')),
    method VARCHAR(50) NOT NULL,
    model_name VARCHAR(100) NOT NULL,
    model_version VARCHAR(50),
    vector_dimensions INTEGER NOT NULL,
    track_count INTEGER NOT NULL,
    umap_params JSONB NOT NULL DEFAULT '{}'::jsonb,
    metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
    catalog_fingerprint VARCHAR(64) NOT NULL,
    failure_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    published_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_sonic_map_versions_status
    ON sonic_map_versions(status, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_sonic_map_single_published
    ON sonic_map_versions ((status)) WHERE status = 'published';
CREATE INDEX IF NOT EXISTS idx_tracks_position_version
    ON tracks(position_version_id);

CREATE TABLE IF NOT EXISTS sonic_map_positions_staging (
    version_id UUID NOT NULL REFERENCES sonic_map_versions(id) ON DELETE CASCADE,
    track_id INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
    position_x FLOAT NOT NULL,
    position_y FLOAT NOT NULL,
    position_z FLOAT NOT NULL,
    PRIMARY KEY (version_id, track_id)
);
