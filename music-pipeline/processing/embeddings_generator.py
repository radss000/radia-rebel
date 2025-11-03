#!/usr/bin/env python3
"""
REBEL Music Database - Audio Embeddings Generator
Generates CLAP embeddings for audio similarity search
"""

import os
import logging
import numpy as np
import psycopg2
from psycopg2.extras import RealDictCursor
import librosa
import soundfile as sf
from typing import Optional
import uuid

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database config
DB_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', 'localhost'),
    'port': int(os.getenv('POSTGRES_PORT', 5432)),
    'database': os.getenv('POSTGRES_DB', 'rebel_music'),
    'user': os.getenv('POSTGRES_USER', 'rebel'),
    'password': os.getenv('POSTGRES_PASSWORD', 'rebel_password')
}

class AudioEmbeddingsGenerator:
    """Generate audio embeddings using CLAP model"""
    
    def __init__(self, db_config: dict):
        self.conn = psycopg2.connect(**db_config)
        self.cursor = self.conn.cursor(cursor_factory=RealDictCursor)
        
        # Initialize CLAP model
        logger.info("Loading CLAP model...")
        try:
            from laion_clap import CLAP_Module
            self.clap = CLAP_Module(enable_fusion=False, amodel='HTSAT-base')
            self.clap.load_ckpt()
            logger.info("✅ CLAP model loaded")
        except ImportError:
            logger.error("CLAP not installed. Install with: pip install laion-clap")
            raise
        
        # Initialize Qdrant (optional)
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
    
    def generate_synthetic_audio(self, track: dict, duration: int = 30) -> Optional[np.ndarray]:
        """
        Generate synthetic audio based on track features
        For demonstration when real audio not available
        """
        try:
            sr = 48000  # Sample rate
            t = np.linspace(0, duration, sr * duration)
            
            # Base frequency from BPM
            bpm = track.get('bpm', 120)
            base_freq = (bpm / 60) * 2  # Convert BPM to Hz
            
            # Generate based on audio features
            energy = track.get('energy', 0.5)
            bass = track.get('bass', 0.5)
            brightness = track.get('brightness', 0.5)
            
            # Bass component (low frequency)
            bass_signal = np.sin(2 * np.pi * base_freq * t) * bass
            
            # Mid component
            mid_signal = np.sin(2 * np.pi * base_freq * 2 * t) * energy * 0.5
            
            # High component (brightness)
            high_signal = np.sin(2 * np.pi * base_freq * 4 * t) * brightness * 0.3
            
            # Combine with noise
            noise = np.random.normal(0, 0.1, len(t)) * (1 - energy)
            
            audio = bass_signal + mid_signal + high_signal + noise
            
            # Normalize
            audio = audio / np.max(np.abs(audio)) * 0.8
            
            return audio.astype(np.float32)
            
        except Exception as e:
            logger.error(f"Error generating synthetic audio: {e}")
            return None
    
    def generate_embedding(self, audio: np.ndarray) -> Optional[np.ndarray]:
        """Generate CLAP embedding from audio array"""
        try:
            # CLAP expects audio at 48kHz
            embedding = self.clap.get_audio_embedding_from_data(
                x=audio,
                use_tensor=False
            )
            return embedding[0]  # Shape: (512,)
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            return None
    
    def save_embedding(self, track_id: int, embedding: np.ndarray) -> str:
        """Save embedding to database and Qdrant"""
        try:
            embedding_id = str(uuid.uuid4())
            
            # Save metadata to PostgreSQL
            self.cursor.execute("""
                INSERT INTO embeddings (id, track_id, model_name, model_version, vector_dimensions)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (track_id) DO UPDATE SET
                    id = EXCLUDED.id,
                    model_name = EXCLUDED.model_name
            """, (embedding_id, track_id, 'clap-htsat-base', '1.0', 512))
            
            # Update track with embedding_id
            self.cursor.execute("""
                UPDATE tracks SET embedding_id = %s WHERE id = %s
            """, (embedding_id, track_id))
            
            # Save vector to Qdrant
            if self.qdrant:
                try:
                    self.qdrant.upsert(
                        collection_name='music_embeddings',
                        points=[{
                            'id': embedding_id,
                            'vector': embedding.tolist(),
                            'payload': {'track_id': track_id}
                        }]
                    )
                except Exception as e:
                    logger.warning(f"Could not save to Qdrant: {e}")
            
            self.conn.commit()
            return embedding_id
            
        except Exception as e:
            logger.error(f"Error saving embedding: {e}")
            self.conn.rollback()
            return None
    
    def process_tracks(self, limit: int = 100):
        """Process tracks and generate embeddings"""
        
        # Get tracks without embeddings
        self.cursor.execute("""
            SELECT id, title, artist, bpm, energy, danceability, 
                   bass, brightness, acousticness
            FROM tracks
            WHERE embedding_id IS NULL
            LIMIT %s
        """, (limit,))
        
        tracks = self.cursor.fetchall()
        logger.info(f"Processing {len(tracks)} tracks...")
        
        success_count = 0
        
        for track in tracks:
            try:
                logger.info(f"Processing: {track['artist']} - {track['title']}")
                
                # Generate synthetic audio based on features
                audio = self.generate_synthetic_audio(track)
                
                if audio is None:
                    continue
                
                # Generate embedding
                embedding = self.generate_embedding(audio)
                
                if embedding is None:
                    continue
                
                # Save
                embedding_id = self.save_embedding(track['id'], embedding)
                
                if embedding_id:
                    logger.info(f"✓ Saved embedding for: {track['title']}")
                    success_count += 1
                
            except Exception as e:
                logger.error(f"Error processing track {track['id']}: {e}")
                continue
        
        logger.info(f"\n✅ Processed {success_count}/{len(tracks)} tracks")
        
    def close(self):
        """Close connections"""
        self.cursor.close()
        self.conn.close()


if __name__ == "__main__":
    logger.info("🎵 REBEL Audio Embeddings Generator\n")
    
    generator = AudioEmbeddingsGenerator(DB_CONFIG)
    
    try:
        # Process in batches
        batch_size = 50
        total_processed = 0
        
        logger.info(f"Processing tracks in batches of {batch_size}...\n")
        
        for batch_num in range(5):  # Max 5 batches (250 tracks)
            logger.info(f"\n{'='*60}")
            logger.info(f"Batch {batch_num + 1}")
            logger.info(f"{'='*60}\n")
            
            generator.process_tracks(limit=batch_size)
            total_processed += batch_size
            
            # Check if done
            generator.cursor.execute(
                "SELECT COUNT(*) FROM tracks WHERE embedding_id IS NULL"
            )
            remaining = generator.cursor.fetchone()['count']
            
            if remaining == 0:
                break
        
        logger.info(f"\n✅ Complete! Processed {total_processed} tracks")
        
    finally:
        generator.close()