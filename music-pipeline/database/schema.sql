-- ============================================================
-- REBEL Music Database - PostgreSQL Schema
-- Database for massive underground music catalog
-- ============================================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================
-- TRACKS TABLE
-- ============================================================
CREATE TABLE tracks (
    id SERIAL PRIMARY KEY,
    
    -- Basic metadata
    title VARCHAR(500) NOT NULL,
    artist VARCHAR(500) NOT NULL,
    album VARCHAR(500),
    year INTEGER,
    duration_sec INTEGER,
    
    -- External IDs for cross-referencing
    musicbrainz_id VARCHAR(36) UNIQUE,
    musicbrainz_release_id VARCHAR(36),
    discogs_id INTEGER,
    spotify_id VARCHAR(22),
    bandcamp_url TEXT,
    youtube_url TEXT,
    deezer_url TEXT,
    
    -- Audio preview
    preview_url TEXT,
    preview_s3_key VARCHAR(200),
    
    -- Embeddings (stored in Qdrant vector DB)
    embedding_id UUID,
    
    -- Label & catalog info
    label VARCHAR(300),
    catalog_number VARCHAR(100),
    
    -- Genre & classification
    genre VARCHAR(100),
    subgenres TEXT[],
    tags TEXT[],
    
    -- Musical characteristics
    bpm INTEGER,
    key VARCHAR(5),
    
    -- AI-generated descriptions
    description_short TEXT,
    description_detailed TEXT,
    discogs_review TEXT,
    
    -- Spotify-like audio features (0-1 scale)
    energy FLOAT CHECK (energy >= 0 AND energy <= 1),
    danceability FLOAT CHECK (danceability >= 0 AND danceability <= 1),
    acousticness FLOAT CHECK (acousticness >= 0 AND acousticness <= 1),
    brightness FLOAT CHECK (brightness >= 0 AND brightness <= 1),
    bass FLOAT CHECK (bass >= 0 AND bass <= 1),
    valence FLOAT CHECK (valence >= 0 AND valence <= 1),
    
    -- 3D position for Sonic Map
    position_x FLOAT,
    position_y FLOAT,
    position_z FLOAT,
    
    -- Visual attributes (for 3D rendering)
    color_r FLOAT DEFAULT 0.7,
    color_g FLOAT DEFAULT 0.3,
    color_b FLOAT DEFAULT 0.9,
    sphere_size FLOAT DEFAULT 1.5,
    emissive_intensity FLOAT DEFAULT 0.5,
    
    -- Metadata
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    
    -- Flags
    is_liked BOOLEAN DEFAULT FALSE,
    is_verified BOOLEAN DEFAULT FALSE,
    is_public BOOLEAN DEFAULT TRUE
);

-- Indexes for fast queries
CREATE INDEX idx_tracks_artist ON tracks(artist);
CREATE INDEX idx_tracks_genre ON tracks(genre);
CREATE INDEX idx_tracks_year ON tracks(year);
CREATE INDEX idx_tracks_label ON tracks(label);
CREATE INDEX idx_tracks_bpm ON tracks(bpm);
CREATE INDEX idx_tracks_musicbrainz ON tracks(musicbrainz_id);
CREATE INDEX idx_tracks_spotify ON tracks(spotify_id);
CREATE INDEX idx_tracks_created ON tracks(created_at DESC);

-- Full-text search index
CREATE INDEX idx_tracks_search ON tracks USING gin(
    to_tsvector('english', 
        coalesce(title, '') || ' ' || 
        coalesce(artist, '') || ' ' || 
        coalesce(album, '')
    )
);

-- ============================================================
-- TRACK LINKS TABLE
-- ============================================================
CREATE TABLE track_links (
    id SERIAL PRIMARY KEY,
    track_id INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
    
    platform VARCHAR(50) NOT NULL,  -- 'spotify', 'bandcamp', 'youtube', 'soundcloud', 'discogs'
    url TEXT NOT NULL,
    link_type VARCHAR(20) NOT NULL, -- 'stream', 'buy', 'download', 'preview'
    
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_track_links_track ON track_links(track_id);
CREATE INDEX idx_track_links_platform ON track_links(platform);

-- ============================================================
-- ARTISTS TABLE (normalized)
-- ============================================================
CREATE TABLE artists (
    id SERIAL PRIMARY KEY,
    name VARCHAR(500) NOT NULL UNIQUE,
    
    -- External IDs
    musicbrainz_id VARCHAR(36) UNIQUE,
    discogs_id INTEGER,
    spotify_id VARCHAR(22),
    
    -- Metadata
    bio TEXT,
    country VARCHAR(100),
    founded_year INTEGER,
    
    -- Stats
    track_count INTEGER DEFAULT 0,
    
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_artists_name ON artists(name);

-- ============================================================
-- LABELS TABLE
-- ============================================================
CREATE TABLE labels (
    id SERIAL PRIMARY KEY,
    name VARCHAR(300) NOT NULL UNIQUE,
    
    -- External IDs
    musicbrainz_id VARCHAR(36) UNIQUE,
    discogs_id INTEGER,
    
    -- Metadata
    country VARCHAR(100),
    founded_year INTEGER,
    description TEXT,
    website TEXT,
    
    -- Stats
    release_count INTEGER DEFAULT 0,
    
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_labels_name ON labels(name);

-- ============================================================
-- USER FAVORITES TABLE (linking to MongoDB users)
-- ============================================================
CREATE TABLE user_favorites (
    id SERIAL PRIMARY KEY,
    
    -- MongoDB user ID (stored as string)
    mongodb_user_id VARCHAR(24) NOT NULL,
    
    track_id INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
    
    created_at TIMESTAMP DEFAULT NOW(),
    
    UNIQUE(mongodb_user_id, track_id)
);

CREATE INDEX idx_favorites_user ON user_favorites(mongodb_user_id);
CREATE INDEX idx_favorites_track ON user_favorites(track_id);

-- ============================================================
-- PROCESSING QUEUE TABLE
-- ============================================================
CREATE TABLE processing_queue (
    id SERIAL PRIMARY KEY,
    track_id INTEGER REFERENCES tracks(id) ON DELETE CASCADE,
    
    task_type VARCHAR(50) NOT NULL,  -- 'embedding', 'description', 'position'
    status VARCHAR(20) DEFAULT 'pending',  -- 'pending', 'processing', 'completed', 'failed'
    
    priority INTEGER DEFAULT 0,
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    
    error_message TEXT,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_queue_status ON processing_queue(status, priority DESC);
CREATE INDEX idx_queue_track ON processing_queue(track_id);

-- ============================================================
-- EMBEDDING METADATA TABLE
-- ============================================================
CREATE TABLE embeddings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    track_id INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
    
    model_name VARCHAR(100) NOT NULL,  -- 'clap-htsat-base', 'mira', etc.
    model_version VARCHAR(50),
    
    -- Vector stored in Qdrant, this is just metadata
    qdrant_point_id UUID,
    vector_dimensions INTEGER,
    
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_embeddings_track ON embeddings(track_id);

-- ============================================================
-- CRAWL HISTORY TABLE
-- ============================================================
CREATE TABLE crawl_history (
    id SERIAL PRIMARY KEY,
    
    source VARCHAR(50) NOT NULL,  -- 'musicbrainz', 'discogs', 'bandcamp'
    query VARCHAR(500),
    
    tracks_found INTEGER DEFAULT 0,
    tracks_saved INTEGER DEFAULT 0,
    
    status VARCHAR(20) DEFAULT 'completed',
    error_message TEXT,
    
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- TRIGGER: Auto-update updated_at
-- ============================================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_tracks_updated_at BEFORE UPDATE ON tracks
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_artists_updated_at BEFORE UPDATE ON artists
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================
-- VIEWS
-- ============================================================

-- View: Tracks with full metadata
CREATE VIEW tracks_full AS
SELECT 
    t.*,
    COALESCE(
        json_agg(
            json_build_object(
                'platform', tl.platform,
                'url', tl.url,
                'type', tl.link_type
            )
        ) FILTER (WHERE tl.id IS NOT NULL),
        '[]'
    ) as links
FROM tracks t
LEFT JOIN track_links tl ON t.id = tl.track_id AND tl.is_active = TRUE
GROUP BY t.id;

-- View: Popular tracks (for discovery)
CREATE VIEW popular_tracks AS
SELECT 
    t.*,
    COUNT(uf.id) as favorite_count
FROM tracks t
LEFT JOIN user_favorites uf ON t.id = uf.track_id
WHERE t.is_public = TRUE
GROUP BY t.id
HAVING COUNT(uf.id) > 0
ORDER BY favorite_count DESC;

-- View: Recently added tracks
CREATE VIEW recent_tracks AS
SELECT * FROM tracks
WHERE is_public = TRUE
ORDER BY created_at DESC
LIMIT 100;

-- ============================================================
-- FUNCTIONS
-- ============================================================

-- Function: Search tracks by text
CREATE OR REPLACE FUNCTION search_tracks(search_query TEXT, result_limit INT DEFAULT 20)
RETURNS TABLE (
    track_id INT,
    title VARCHAR,
    artist VARCHAR,
    album VARCHAR,
    rank REAL
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        t.id,
        t.title,
        t.artist,
        t.album,
        ts_rank(
            to_tsvector('english', 
                coalesce(t.title, '') || ' ' || 
                coalesce(t.artist, '') || ' ' || 
                coalesce(t.album, '')
            ),
            plainto_tsquery('english', search_query)
        ) as rank
    FROM tracks t
    WHERE to_tsvector('english', 
            coalesce(t.title, '') || ' ' || 
            coalesce(t.artist, '') || ' ' || 
            coalesce(t.album, '')
        ) @@ plainto_tsquery('english', search_query)
    ORDER BY rank DESC
    LIMIT result_limit;
END;
$$ LANGUAGE plpgsql;

-- Function: Get tracks by genre cluster
CREATE OR REPLACE FUNCTION get_genre_cluster(input_genre VARCHAR, result_limit INT DEFAULT 100)
RETURNS TABLE (
    track_id INT,
    title VARCHAR,
    artist VARCHAR,
    genre VARCHAR
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        t.id,
        t.title,
        t.artist,
        t.genre
    FROM tracks t
    WHERE t.genre ILIKE '%' || input_genre || '%'
       OR input_genre = ANY(t.tags)
    LIMIT result_limit;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- SAMPLE DATA (Optional - for testing)
-- ============================================================

-- INSERT INTO tracks (title, artist, genre, year, bpm, description_short) VALUES
-- ('Untitled A1', 'Dopplereffekt', 'Electro', 1997, 125, 'Mechanistic drums with icy synth sequences.'),
-- ('Spain', 'Chick Corea', 'Jazz Fusion', 1972, 140, 'Classic jazz fusion with intricate piano work.');

-- ============================================================
-- GRANTS (adjust based on your user setup)
-- ============================================================

-- Example: Grant permissions to application user
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO rebel_app;
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO rebel_app;

-- ============================================================
-- END OF SCHEMA
-- ============================================================
