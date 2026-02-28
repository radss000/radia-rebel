#!/usr/bin/env python3
"""
REBEL Music Database - Sonic Map Position Generator
Generates 3D positions using UMAP dimensionality reduction on embeddings
"""

import os
import logging
import numpy as np
import psycopg2
from psycopg2.extras import RealDictCursor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', 'localhost'),
    'port': int(os.getenv('POSTGRES_PORT', 5432)),
    'database': os.getenv('POSTGRES_DB', 'rebel_music'),
    'user': os.getenv('POSTGRES_USER', 'rebel'),
    'password': os.getenv('POSTGRES_PASSWORD', 'rebel_password')
}

class SonicMapGenerator:
    """Generate 3D positions for Sonic Map visualization"""
    
    def __init__(self, db_config: dict):
        self.conn = psycopg2.connect(**db_config)
        self.cursor = self.conn.cursor(cursor_factory=RealDictCursor)
        
        # Try to connect to Qdrant
        self.qdrant = None
        try:
            from qdrant_client import QdrantClient
            self.qdrant = QdrantClient(
                host=os.getenv('QDRANT_HOST', 'localhost'),
                port=int(os.getenv('QDRANT_PORT', 6333))
            )
            logger.info("✅ Connected to Qdrant")
        except Exception as e:
            logger.warning(f"⚠️  Qdrant not available: {e}")
    
    def generate_positions_from_features(self):
        """Generate positions using audio features (fallback method)"""
        logger.info("Generating positions from audio features...")
        
        # Get all tracks with features
        self.cursor.execute("""
            SELECT id, energy, danceability, acousticness, 
                   bass, brightness, bpm, genre
            FROM tracks
            WHERE energy IS NOT NULL
        """)
        
        tracks = self.cursor.fetchall()
        logger.info(f"Processing {len(tracks)} tracks")
        
        if len(tracks) == 0:
            logger.error("No tracks with audio features found!")
            return
        
        # Create feature matrix
        features = []
        track_ids = []
        
        for track in tracks:
            feature_vector = [
                track['energy'] or 0.5,
                track['danceability'] or 0.5,
                track['acousticness'] or 0.5,
                track['bass'] or 0.5,
                track['brightness'] or 0.5,
                (track['bpm'] or 120) / 200.0  # Normalize BPM
            ]
            features.append(feature_vector)
            track_ids.append(track['id'])
        
        features = np.array(features)
        
        # Try UMAP first, fallback to PCA
        try:
            import umap
            logger.info("Using UMAP for dimensionality reduction...")
            
            reducer = umap.UMAP(
                n_components=3,
                n_neighbors=15,
                min_dist=0.1,
                metric='euclidean',
                random_state=42
            )
            positions_3d = reducer.fit_transform(features)
            
        except ImportError:
            logger.warning("UMAP not available, using PCA...")
            from sklearn.decomposition import PCA
            from sklearn.preprocessing import StandardScaler
            
            # Scale features
            scaler = StandardScaler()
            features_scaled = scaler.fit_transform(features)
            
            # PCA to 3D
            pca = PCA(n_components=3, random_state=42)
            positions_3d = pca.fit_transform(features_scaled)
            
            logger.info(f"PCA explained variance: {pca.explained_variance_ratio_}")
        
        # Scale positions to reasonable range (-300 to 300)
        positions_3d = self._scale_positions(positions_3d)
        
        # Save to database
        self._save_positions(track_ids, positions_3d)
        
        logger.info(f"✅ Generated positions for {len(track_ids)} tracks")
    
    def generate_positions_from_embeddings(self):
        """Generate positions using CLAP embeddings from Qdrant"""
        if not self.qdrant:
            logger.warning("Qdrant not available, using audio features instead")
            return self.generate_positions_from_features()
        
        logger.info("Generating positions from CLAP embeddings...")
        
        try:
            # Fetch all embeddings from Qdrant
            points = self.qdrant.scroll(
                collection_name='music_embeddings',
                limit=10000,
                with_payload=True,
                with_vectors=True
            )[0]
            
            if len(points) == 0:
                logger.warning("No embeddings in Qdrant, using features instead")
                return self.generate_positions_from_features()
            
            logger.info(f"Found {len(points)} embeddings")
            
            # Extract embeddings and track IDs
            embeddings = np.array([p.vector for p in points])
            track_ids = [p.payload['track_id'] for p in points]
            
            # Use UMAP for dimensionality reduction
            try:
                import umap
                reducer = umap.UMAP(
                    n_components=3,
                    n_neighbors=min(15, len(embeddings) - 1),
                    min_dist=0.1,
                    metric='cosine',
                    random_state=42
                )
                positions_3d = reducer.fit_transform(embeddings)
            except ImportError:
                logger.warning("UMAP not available, using PCA...")
                from sklearn.decomposition import PCA
                pca = PCA(n_components=3, random_state=42)
                positions_3d = pca.fit_transform(embeddings)
            
            # Scale positions
            positions_3d = self._scale_positions(positions_3d)
            
            # Save to database
            self._save_positions(track_ids, positions_3d)
            
            logger.info(f"✅ Generated positions for {len(track_ids)} tracks")
            
        except Exception as e:
            logger.error(f"Error with Qdrant: {e}")
            logger.info("Falling back to audio features method...")
            return self.generate_positions_from_features()
    
    def _scale_positions(self, positions: np.ndarray, scale: float = 300.0) -> np.ndarray:
        """Scale positions to reasonable range"""
        # Center around origin
        positions = positions - positions.mean(axis=0)
        
        # Scale to fit in range
        max_val = np.abs(positions).max()
        if max_val > 0:
            positions = (positions / max_val) * scale
        
        return positions
    
    def _save_positions(self, track_ids: list, positions: np.ndarray):
        """Save positions to database"""
        for track_id, (x, y, z) in zip(track_ids, positions):
            try:
                self.cursor.execute("""
                    UPDATE tracks
                    SET position_x = %s,
                        position_y = %s,
                        position_z = %s,
                        updated_at = NOW()
                    WHERE id = %s
                """, (float(x), float(y), float(z), int(track_id)))
            except Exception as e:
                logger.error(f"Error saving position for track {track_id}: {e}")
        
        self.conn.commit()
    
    def assign_colors_by_genre(self):
        """Assign colors based on genre"""
        logger.info("Assigning colors by genre...")
        
        # Genre color mapping
        genre_colors = {
            'Techno': (0.8, 0.2, 0.2),
            'Minimal Techno': (0.9, 0.3, 0.3),
            'House': (0.9, 0.5, 0.2),
            'Deep House': (0.8, 0.6, 0.3),
            'IDM': (0.2, 0.8, 0.9),
            'Ambient': (0.5, 0.7, 0.9),
            'Dubstep': (0.1, 0.6, 0.8),
            'Drum & Bass': (0.1, 0.5, 0.7),
            'Jungle': (0.2, 0.6, 0.6),
            'Hip-Hop': (0.2, 0.7, 0.3),
            'Jazz': (0.7, 0.3, 0.9),
            'Jazz Fusion': (0.8, 0.4, 0.9),
            'Breakbeat': (0.9, 0.5, 0.2),
            'Trance': (0.3, 0.8, 0.5),
            'Acid House': (0.9, 0.5, 0.2),
        }
        
        default_color = (0.6, 0.6, 0.6)
        
        for genre, (r, g, b) in genre_colors.items():
            self.cursor.execute("""
                UPDATE tracks
                SET color_r = %s, color_g = %s, color_b = %s
                WHERE genre ILIKE %s
            """, (r, g, b, f'%{genre}%'))
        
        # Set default for tracks without matched genre
        self.cursor.execute("""
            UPDATE tracks
            SET color_r = %s, color_g = %s, color_b = %s
            WHERE color_r IS NULL
        """, default_color)
        
        self.conn.commit()
        logger.info("✅ Colors assigned")
    
    def close(self):
        """Close database connection"""
        self.cursor.close()
        self.conn.close()


if __name__ == "__main__":
    logger.info("🗺️  REBEL Sonic Map Position Generator\n")
    
    generator = SonicMapGenerator(DB_CONFIG)
    
    try:
        # Generate positions (try embeddings first, fallback to features)
        generator.generate_positions_from_embeddings()
        
        # Assign colors by genre
        generator.assign_colors_by_genre()
        
        # Print stats
        generator.cursor.execute("""
            SELECT 
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE position_x IS NOT NULL) as with_positions
            FROM tracks
        """)
        stats = generator.cursor.fetchone()
        
        logger.info(f"\n📊 Stats:")
        logger.info(f"  Total tracks: {stats['total']}")
        logger.info(f"  With positions: {stats['with_positions']}")
        
        logger.info("\n✅ Sonic Map generation complete!")
        
    finally:
        generator.close()