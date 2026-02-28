#!/usr/bin/env python3
"""
REBEL Music Database - Description Generator
Generates detailed, technical track descriptions in Discogs review style
Uses Claude AI for natural, expert-level descriptions
"""

import psycopg2
from psycopg2.extras import RealDictCursor
from anthropic import Anthropic
import logging
import time
from typing import Dict, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DescriptionGenerator:
    def __init__(self, db_config: Dict, anthropic_api_key: str):
        """Initialize with database and Anthropic API"""
        self.conn = psycopg2.connect(**db_config)
        self.cursor = self.conn.cursor(cursor_factory=RealDictCursor)
        self.client = Anthropic(api_key=anthropic_api_key)
        
    def generate_descriptions_batch(self, limit: int = 100):
        """Generate descriptions for tracks without them"""
        
        # Get tracks needing descriptions
        self.cursor.execute("""
            SELECT id, title, artist, album, year, label, genre, 
                   tags, bpm, energy, danceability, acousticness, 
                   brightness, bass
            FROM tracks 
            WHERE description_detailed IS NULL 
            LIMIT %s
        """, (limit,))
        
        tracks = self.cursor.fetchall()
        logger.info(f"Generating descriptions for {len(tracks)} tracks")
        
        for track in tracks:
            try:
                # Generate description
                description = self._generate_description(track)
                
                if description:
                    # Save to database
                    self._save_description(track['id'], description)
                    logger.info(f"✓ Generated: {track['artist']} - {track['title']}")
                
                time.sleep(1)  # Rate limit for API
                
            except Exception as e:
                logger.error(f"Error generating description for track {track['id']}: {e}")
                continue
        
        self.conn.commit()
        logger.info("Batch complete")
    
    def _generate_description(self, track: Dict) -> Optional[str]:
        """Generate Discogs-style description using Claude"""
        
        # Build context from available data
        context_parts = []
        
        if track.get('genre'):
            context_parts.append(f"Genre: {track['genre']}")
        
        if track.get('tags'):
            tags = ', '.join(track['tags'][:5])  # Top 5 tags
            context_parts.append(f"Tags: {tags}")
        
        # Audio characteristics
        if track.get('bpm'):
            context_parts.append(f"BPM: {track['bpm']}")
        
        audio_chars = []
        if track.get('energy') is not None:
            energy_desc = self._interpret_metric(track['energy'], 
                ['restrained', 'moderate', 'energetic', 'intense'])
            audio_chars.append(f"Energy: {energy_desc}")
        
        if track.get('danceability') is not None:
            dance_desc = self._interpret_metric(track['danceability'],
                ['experimental', 'moderate groove', 'danceable', 'peak-time'])
            audio_chars.append(f"Danceability: {dance_desc}")
        
        if track.get('bass') is not None:
            bass_desc = self._interpret_metric(track['bass'],
                ['minimal bass', 'balanced', 'bass-forward', 'sub-heavy'])
            audio_chars.append(f"Bass: {bass_desc}")
        
        if track.get('brightness') is not None:
            bright_desc = self._interpret_metric(track['brightness'],
                ['dark/murky', 'balanced', 'bright', 'crystalline'])
            audio_chars.append(f"Tonal character: {bright_desc}")
        
        if audio_chars:
            context_parts.append("Audio characteristics:\n- " + "\n- ".join(audio_chars))
        
        context = "\n".join(context_parts)
        
        # Construct prompt
        prompt = f"""You are an experienced record collector and music journalist writing technical reviews in the style of detailed Discogs reviews. Write a professional, insightful description for this track.

Track: "{track['title']}"
Artist: {track['artist']}
{f"Label: {track['label']}" if track.get('label') else ""}
{f"Year: {track['year']}" if track.get('year') else ""}

{context}

Write a description (2-4 sentences) that:
1. Describes the sonic characteristics, mood, and production quality
2. Highlights standout musical elements (synths, drums, bassline, arrangement)
3. Mentions dancefloor effectiveness or listening context
4. References production techniques or genre influences where relevant

Style requirements:
- Technical but accessible language
- Specific musical terminology
- No emojis or casual expressions
- No explicit ratings or scores
- Convey quality through descriptive language
- Professional, minimalist tone

Example style reference:
"Brooding synths layered over precise, mechanistic drums establish the track's hypnotic foundation. The acid line introduced at the two-minute mark adds necessary tension, elevating what begins as a functional tool into something more memorable. Built for deep into the night, the stripped-back aesthetic allows the groove to dominate."

Write only the description, no preamble or additional commentary."""

        try:
            # Call Claude API
            response = self.client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=400,
                temperature=0.7,
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )
            
            description = response.content[0].text.strip()
            
            # Clean up any unwanted formatting
            description = description.replace('"', '')
            description = description.strip()
            
            return description
            
        except Exception as e:
            logger.error(f"API error: {e}")
            return None
    
    def _interpret_metric(self, value: float, labels: list) -> str:
        """Convert 0-1 metric to descriptive label"""
        if value < 0.25:
            return labels[0]
        elif value < 0.5:
            return labels[1]
        elif value < 0.75:
            return labels[2]
        else:
            return labels[3]
    
    def _save_description(self, track_id: int, description: str):
        """Save generated description to database"""
        try:
            self.cursor.execute("""
                UPDATE tracks 
                SET description_detailed = %s,
                    description_short = %s,
                    updated_at = NOW()
                WHERE id = %s
            """, (
                description,
                description[:200] + '...' if len(description) > 200 else description,
                track_id
            ))
        except psycopg2.Error as e:
            logger.error(f"Database error: {e}")
            self.conn.rollback()
    
    def close(self):
        """Close database connection"""
        self.cursor.close()
        self.conn.close()


# Multi-track album description generator
class AlbumDescriptionGenerator(DescriptionGenerator):
    """Specialized generator for album reviews (multiple tracks)"""
    
    def generate_album_description(self, release_id: str):
        """Generate full album review with per-track descriptions"""
        
        # Get all tracks from release
        self.cursor.execute("""
            SELECT id, title, artist, album, year, label, position,
                   genre, tags, bpm, energy, danceability, acousticness,
                   brightness, bass
            FROM tracks 
            WHERE musicbrainz_release_id = %s
            ORDER BY position
        """, (release_id,))
        
        tracks = self.cursor.fetchall()
        
        if not tracks:
            logger.warning(f"No tracks found for release {release_id}")
            return None
        
        # Build album context
        album_info = tracks[0]  # Get metadata from first track
        
        # Generate per-track descriptions
        track_descriptions = []
        
        for track in tracks:
            desc = self._generate_track_in_album_context(track, len(tracks))
            if desc:
                track_descriptions.append(f"{track['position']}: {track['title']}. {desc}")
        
        # Combine into full album review
        full_review = "\n\n".join(track_descriptions)
        
        logger.info(f"Generated album review for: {album_info['album']}")
        return full_review
    
    def _generate_track_in_album_context(self, track: Dict, total_tracks: int) -> str:
        """Generate description for track within album context"""
        
        # Simpler prompt for per-track descriptions
        prompt = f"""Write a concise, technical description (1-2 sentences) for this track in an album review.

Track {track['position']} of {total_tracks}: "{track['title']}"
{f"BPM: {track['bpm']}" if track.get('bpm') else ""}
Genre: {track.get('genre', 'Electronic')}

Focus on:
- Sonic character and production
- Notable elements
- How it fits the album flow

Style: Technical, concise, no emojis. Similar to professional Discogs reviews.

Example: "Deep, rolling bassline anchors this late-night techno burner. Sparse percussion and a hypnotic synth lead build gradually, creating peak-time warehouse energy."

Write only the description."""

        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=200,
                temperature=0.7,
                messages=[{"role": "user", "content": prompt}]
            )
            
            return response.content[0].text.strip()
            
        except Exception as e:
            logger.error(f"Error generating track description: {e}")
            return f"Track {track['position']} - production details unavailable."


if __name__ == "__main__":
    import os
    
    # Configuration
    DB_CONFIG = {
        'host': 'localhost',
        'port': 5432,
        'database': 'rebel_music',
        'user': 'rebel',
        'password': 'your_password'
    }
    
    ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')
    
    if not ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY environment variable not set")
    
    # Generate descriptions
    generator = DescriptionGenerator(DB_CONFIG, ANTHROPIC_API_KEY)
    
    try:
        # Process in batches
        total_processed = 0
        batch_size = 50
        
        while total_processed < 1000:  # Limit for demo
            logger.info(f"\nProcessing batch {total_processed // batch_size + 1}")
            generator.generate_descriptions_batch(limit=batch_size)
            total_processed += batch_size
            
            time.sleep(5)  # Pause between batches
            
    finally:
        generator.close()
    
    logger.info(f"\n✅ Generated {total_processed} descriptions")
