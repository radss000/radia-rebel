#!/usr/bin/env python3
"""
REBEL Music Database - Audio Features Calculator
Estimates audio features (energy, danceability, etc.) based on genre/tags
Since MusicBrainz doesn't provide these, we estimate them intelligently
"""

import os
import logging
import psycopg2
from psycopg2.extras import RealDictCursor
import random
from typing import Dict, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', 'localhost'),
    'port': int(os.getenv('POSTGRES_PORT', 5432)),
    'database': os.getenv('POSTGRES_DB', 'rebel_music'),
    'user': os.getenv('POSTGRES_USER', 'rebel'),
    'password': os.getenv('POSTGRES_PASSWORD', 'rebel_password')
}

# Genre-based feature profiles
GENRE_PROFILES = {
    'electronic': {'energy': 0.75, 'danceability': 0.80, 'acousticness': 0.10, 'bass': 0.75, 'brightness': 0.60},
    'techno': {'energy': 0.85, 'danceability': 0.85, 'acousticness': 0.05, 'bass': 0.80, 'brightness': 0.45},
    'minimal techno': {'energy': 0.70, 'danceability': 0.80, 'acousticness': 0.05, 'bass': 0.75, 'brightness': 0.40},
    'house': {'energy': 0.75, 'danceability': 0.85, 'acousticness': 0.10, 'bass': 0.70, 'brightness': 0.55},
    'deep house': {'energy': 0.65, 'danceability': 0.75, 'acousticness': 0.15, 'bass': 0.75, 'brightness': 0.50},
    'idm': {'energy': 0.60, 'danceability': 0.55, 'acousticness': 0.15, 'bass': 0.50, 'brightness': 0.65},
    'ambient': {'energy': 0.30, 'danceability': 0.20, 'acousticness': 0.70, 'bass': 0.30, 'brightness': 0.75},
    'dubstep': {'energy': 0.80, 'danceability': 0.75, 'acousticness': 0.05, 'bass': 0.90, 'brightness': 0.40},
    'drum and bass': {'energy': 0.90, 'danceability': 0.80, 'acousticness': 0.05, 'bass': 0.85, 'brightness': 0.60},
    'jungle': {'energy': 0.85, 'danceability': 0.75, 'acousticness': 0.05, 'bass': 0.85, 'brightness': 0.55},
    'hip-hop': {'energy': 0.70, 'danceability': 0.75, 'acousticness': 0.15, 'bass': 0.80, 'brightness': 0.45},
    'hip hop': {'energy': 0.70, 'danceability': 0.75, 'acousticness': 0.15, 'bass': 0.80, 'brightness': 0.45},
    'jazz': {'energy': 0.55, 'danceability': 0.50, 'acousticness': 0.75, 'bass': 0.50, 'brightness': 0.70},
    'jazz fusion': {'energy': 0.65, 'danceability': 0.55, 'acousticness': 0.60, 'bass': 0.60, 'brightness': 0.65},
    'breakbeat': {'energy': 0.80, 'danceability': 0.80, 'acousticness': 0.10, 'bass': 0.75, 'brightness': 0.55},
    'trance': {'energy': 0.80, 'danceability': 0.85, 'acousticness': 0.05, 'bass': 0.70, 'brightness': 0.70},
    'acid house': {'energy': 0.85, 'danceability': 0.90, 'acousticness': 0.05, 'bass': 0.75, 'brightness': 0.60},
    'experimental': {'energy': 0.50, 'danceability': 0.35, 'acousticness': 0.40, 'bass': 0.45, 'brightness': 0.60},
    'indie': {'energy': 0.60, 'danceability': 0.55, 'acousticness': 0.50, 'bass': 0.50, 'brightness': 0.65},
    'rock': {'energy': 0.75, 'danceability': 0.50, 'acousticness': 0.20, 'bass': 0.65, 'brightness': 0.70},
    'pop': {'energy': 0.70, 'danceability': 0.75, 'acousticness': 0.25, 'bass': 0.60, 'brightness': 0.75},
}

# Default profile
DEFAULT_PROFILE = {'energy': 0.60, 'danceability': 0.60, 'acousticness': 0.40, 'bass': 0.60, 'brightness': 0.60}

class AudioFeaturesCalculator:
    """Calculate audio features for tracks based on metadata"""
    
    def __init__(self, db_config: dict):
        self.conn = psycopg2.connect(**db_config)
        self.cursor = self.conn.cursor(cursor_factory=RealDictCursor)
    
    def calculate_features(self):
        """Calculate features for all tracks"""
        
        # Get tracks without features
        self.cursor.execute("""
            SELECT id, artist, title, tags, duration_sec
            FROM tracks
            WHERE energy IS NULL
        """)
        
        tracks = self.cursor.fetchall()
        logger.info(f"Calculating features for {len(tracks)} tracks...")
        
        if len(tracks) == 0:
            logger.info("All tracks already have features!")
            return
        
        success_count = 0
        
        for track in tracks:
            try:
                # Extract genre from tags
                genre = self._extract_genre(track['tags'])
                
                # Get base features from genre
                features = self._get_genre_features(genre)
                
                # Add variation (±10%)
                features = self._add_variation(features)
                
                # Estimate BPM from genre
                bpm = self._estimate_bpm(genre)
                
                # Update database
                self.cursor.execute("""
                    UPDATE tracks
                    SET 
                        energy = %s,
                        danceability = %s,
                        acousticness = %s,
                        bass = %s,
                        brightness = %s,
                        bpm = %s,
                        genre = %s,
                        updated_at = NOW()
                    WHERE id = %s
                """, (
                    features['energy'],
                    features['danceability'],
                    features['acousticness'],
                    features['bass'],
                    features['brightness'],
                    bpm,
                    genre,
                    track['id']
                ))
                
                success_count += 1
                
                if success_count % 50 == 0:
                    self.conn.commit()
                    logger.info(f"  ✓ Processed {success_count}/{len(tracks)} tracks")
                
            except Exception as e:
                logger.error(f"Error processing track {track['id']}: {e}")
                continue
        
        self.conn.commit()
        logger.info(f"\n✅ Calculated features for {success_count} tracks")
    
    def _extract_genre(self, tags: list) -> str:
        """Extract main genre from tags"""
        if not tags:
            return 'electronic'
        
        # Priority order for genre detection
        genre_keywords = [
            'techno', 'house', 'ambient', 'idm', 'dubstep',
            'drum and bass', 'jungle', 'breakbeat', 'trance',
            'hip-hop', 'hip hop', 'jazz', 'experimental', 'indie', 'rock', 'pop'
        ]
        
        # Convert tags to lowercase string
        tags_str = ' '.join(tags).lower()
        
        # Find first matching genre
        for keyword in genre_keywords:
            if keyword in tags_str:
                return keyword
        
        # Fallback
        return 'electronic'
    
    def _get_genre_features(self, genre: str) -> Dict[str, float]:
        """Get feature profile for genre"""
        genre_lower = genre.lower()
        
        # Try exact match
        if genre_lower in GENRE_PROFILES:
            return GENRE_PROFILES[genre_lower].copy()
        
        # Try partial match
        for key in GENRE_PROFILES:
            if key in genre_lower or genre_lower in key:
                return GENRE_PROFILES[key].copy()
        
        # Default
        return DEFAULT_PROFILE.copy()
    
    def _add_variation(self, features: Dict[str, float]) -> Dict[str, float]:
        """Add random variation to features (±10%)"""
        varied = {}
        for key, value in features.items():
            variation = random.uniform(-0.10, 0.10)
            varied[key] = max(0.0, min(1.0, value + variation))
        return varied
    
    def _estimate_bpm(self, genre: str) -> int:
        """Estimate BPM based on genre"""
        genre_lower = genre.lower()
        
        bpm_ranges = {
            'ambient': (60, 90),
            'hip-hop': (85, 105),
            'hip hop': (85, 105),
            'house': (120, 130),
            'deep house': (118, 125),
            'techno': (125, 140),
            'minimal techno': (125, 135),
            'trance': (130, 145),
            'drum and bass': (160, 180),
            'jungle': (160, 175),
            'dubstep': (135, 145),
            'breakbeat': (125, 140),
            'idm': (100, 140),
            'jazz': (90, 140),
        }
        
        # Find matching range
        for key, (min_bpm, max_bpm) in bpm_ranges.items():
            if key in genre_lower:
                return random.randint(min_bpm, max_bpm)
        
        # Default
        return random.randint(100, 130)
    
    def assign_colors_by_genre(self):
        """Assign colors based on detected genre"""
        logger.info("Assigning colors by genre...")
        
        genre_colors = {
            'techno': (0.8, 0.2, 0.2),
            'minimal techno': (0.9, 0.3, 0.3),
            'house': (0.9, 0.5, 0.2),
            'deep house': (0.8, 0.6, 0.3),
            'idm': (0.2, 0.8, 0.9),
            'ambient': (0.5, 0.7, 0.9),
            'dubstep': (0.1, 0.6, 0.8),
            'drum and bass': (0.1, 0.5, 0.7),
            'jungle': (0.2, 0.6, 0.6),
            'hip-hop': (0.2, 0.7, 0.3),
            'hip hop': (0.2, 0.7, 0.3),
            'jazz': (0.7, 0.3, 0.9),
            'jazz fusion': (0.8, 0.4, 0.9),
            'breakbeat': (0.9, 0.5, 0.2),
            'trance': (0.3, 0.8, 0.5),
            'experimental': (0.6, 0.6, 0.6),
        }
        
        default_color = (0.6, 0.6, 0.6)
        
        for genre, (r, g, b) in genre_colors.items():
            self.cursor.execute("""
                UPDATE tracks
                SET color_r = %s, color_g = %s, color_b = %s
                WHERE genre ILIKE %s AND color_r IS NULL
            """, (r, g, b, f'%{genre}%'))
        
        # Default for unmatched
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
    logger.info("🎵 REBEL Audio Features Calculator\n")
    
    calculator = AudioFeaturesCalculator(DB_CONFIG)
    
    try:
        # Calculate features
        calculator.calculate_features()
        
        # Assign colors
        calculator.assign_colors_by_genre()
        
        # Stats
        calculator.cursor.execute("""
            SELECT 
                genre,
                COUNT(*) as count,
                ROUND(AVG(energy)::numeric, 2) as avg_energy,
                ROUND(AVG(danceability)::numeric, 2) as avg_dance,
                ROUND(AVG(bpm)::numeric, 0) as avg_bpm
            FROM tracks
            WHERE genre IS NOT NULL
            GROUP BY genre
            ORDER BY count DESC
            LIMIT 10
        """)
        
        stats = calculator.cursor.fetchall()
        
        logger.info("\n📊 Genre Statistics:")
        logger.info(f"{'Genre':<20} {'Tracks':<8} {'Energy':<8} {'Dance':<8} {'BPM':<8}")
        logger.info("="*60)
        for stat in stats:
            logger.info(f"{stat['genre']:<20} {stat['count']:<8} {stat['avg_energy']:<8} {stat['avg_dance']:<8} {stat['avg_bpm']:<8}")
        
        logger.info("\n✅ Feature calculation complete!")
        
    finally:
        calculator.close()