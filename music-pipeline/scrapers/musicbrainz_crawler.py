#!/usr/bin/env python3
"""
REBEL Music Database - MusicBrainz Crawler
Collects underground music metadata from MusicBrainz API
"""

import musicbrainzngs
import time
import json
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import List, Dict, Optional
import logging
import requests
from urllib.parse import quote
import re

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configure MusicBrainz
musicbrainzngs.set_useragent("REBEL", "1.0", "contact@rebel-music.com")
musicbrainzngs.set_rate_limit(limit_or_interval=1.0)  # 1 request per second

class MusicBrainzCrawler:
    def __init__(self, db_config: Dict[str, str]):
        """Initialize crawler with database connection"""
        self.conn = psycopg2.connect(**db_config)
        self.cursor = self.conn.cursor(cursor_factory=RealDictCursor)
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'REBEL-MusicCrawler/1.0 (+contact@rebel-music.com)'
        })
        self.discogs_cache: Dict[int, Dict[str, Optional[str]]] = {}
        self.deezer_cache: Dict[str, Dict[str, Optional[str]]] = {}
        self.youtube_cache: Dict[str, Optional[str]] = {}
        
    def crawl_label(self, label_name: str, limit: int = 1000):
        """Crawl all releases from a specific label"""
        logger.info(f"Starting crawl for label: {label_name}")
        
        offset = 0
        batch_size = 100
        total_saved = 0
        
        while offset < limit:
            try:
                # Search releases by label
                result = musicbrainzngs.search_releases(
                    label=label_name,
                    limit=batch_size,
                    offset=offset
                )
                
                releases = result.get('release-list', [])
                if not releases:
                    break
                
                logger.info(f"Processing {len(releases)} releases (offset {offset})")
                
                for release in releases:
                    try:
                        # Get full release details
                        release_detail = self._get_release_details(release['id'])
                        
                        if release_detail:
                            # Extract tracks from release
                            tracks = self._extract_tracks(release_detail)
                            
                            for track in tracks:
                                saved = self._save_track(track)
                                if saved:
                                    total_saved += 1
                        
                        time.sleep(1)  # Rate limit
                        
                    except Exception as e:
                        logger.error(f"Error processing release {release.get('id')}: {e}")
                        continue
                
                offset += batch_size
                
            except musicbrainzngs.WebServiceError as e:
                logger.error(f"MusicBrainz API error: {e}")
                time.sleep(5)
                continue
        
        logger.info(f"Crawl complete. Saved {total_saved} tracks from {label_name}")
        self.conn.commit()
        
    def _get_release_details(self, release_id: str) -> Optional[Dict]:
        """Get full release details including recordings"""
        try:
            result = musicbrainzngs.get_release_by_id(
                release_id,
                includes=[
                    'artists',
                    'labels',
                    'recordings',
                    'release-groups',
                    'url-rels',
                    'recording-level-rels'
                ]
            )
            return result.get('release')
        except Exception as e:
            logger.error(f"Error fetching release {release_id}: {e}")
            return None
    
    def _extract_tracks(self, release: Dict) -> List[Dict]:
        """Extract individual tracks from release"""
        tracks = []
        
        # Get release metadata
        album_title = release.get('title', 'Unknown Album')
        artist_name = self._get_artist_name(release)
        year = self._extract_year(release)
        label = self._get_label_name(release)
        
        # Extract tracks from medium list
        media = release.get('medium-list', [])
        for medium in media:
            track_list = medium.get('track-list', [])
            
            for track_entry in track_list:
                recording = track_entry.get('recording', {})
                
                links = self._collect_links(release.get('url-relation-list'))
                links.update(self._collect_links(recording.get('url-relation-list')))
                
                track_data = {
                    'title': recording.get('title', 'Unknown'),
                    'artist': artist_name,
                    'album': album_title,
                    'year': year,
                    'label': label,
                    'musicbrainz_id': recording.get('id'),
                    'musicbrainz_release_id': release.get('id'),
                    'position': track_entry.get('position', '1'),
                    'duration_sec': self._parse_duration(recording.get('length')),
                    'tags': self._extract_tags(recording),
                    'bandcamp_url': links.get('bandcamp_url'),
                    'youtube_url': links.get('youtube_url'),
                    'deezer_url': links.get('deezer_url'),
                    'discogs_id': links.get('discogs_id')
                }
                
                tracks.append(track_data)
        
        return tracks
    
    def _get_artist_name(self, release: Dict) -> str:
        """Extract primary artist name"""
        artist_credit = release.get('artist-credit', [])
        if artist_credit:
            return artist_credit[0].get('artist', {}).get('name', 'Unknown Artist')
        return 'Unknown Artist'
    
    def _extract_year(self, release: Dict) -> Optional[int]:
        """Extract release year"""
        date = release.get('date', '')
        if date:
            try:
                return int(date.split('-')[0])
            except (ValueError, IndexError):
                pass
        
        # Try release group date
        release_group = release.get('release-group', {})
        date = release_group.get('first-release-date', '')
        if date:
            try:
                return int(date.split('-')[0])
            except (ValueError, IndexError):
                pass
        
        return None
    
    def _get_label_name(self, release: Dict) -> Optional[str]:
        """Extract label name"""
        label_info = release.get('label-info-list', [])
        if label_info:
            label = label_info[0].get('label', {})
            return label.get('name')
        return None
    
    def _parse_duration(self, length_ms: Optional[int]) -> Optional[int]:
        """Convert milliseconds to seconds"""
        if length_ms:
            try:
                # Handle both int and string
                if isinstance(length_ms, str):
                    length_ms = int(length_ms)
                return int(length_ms / 1000)
            except (ValueError, TypeError):
                return None
        return None
    
    def _extract_tags(self, recording: Dict) -> List[str]:
        """Extract genre/style tags"""
        tags = []
        tag_list = recording.get('tag-list', [])
        for tag in tag_list:
            tags.append(tag.get('name', ''))
        return tags

    def _collect_links(self, relation_list: Optional[List[Dict]]) -> Dict[str, Optional[str]]:
        """Extract external links from relation list"""
        links: Dict[str, Optional[str]] = {}
        if not relation_list:
            return links
        
        for relation in relation_list:
            url_info = relation.get('url') or {}
            url = url_info.get('resource') or relation.get('target')
            if not url:
                continue
            
            lowered = url.lower()
            
            if 'bandcamp.com' in lowered and 'bandcamp.com/EmbeddedPlayer' not in lowered:
                links.setdefault('bandcamp_url', url)
            elif 'youtube.com' in lowered or 'youtu.be' in lowered:
                links.setdefault('youtube_url', url)
            elif 'deezer.com' in lowered:
                links.setdefault('deezer_url', url)
            elif 'discogs.com' in lowered:
                match = re.search(r'/release/(\d+)', url)
                if match:
                    links.setdefault('discogs_id', int(match.group(1)))
                else:
                    match = re.search(r'/master/(\d+)', url)
                    if match:
                        links.setdefault('discogs_id', int(match.group(1)))
        return links
    
    def _normalize_text(self, value: Optional[str]) -> str:
        if not value:
            return ''
        value = value.lower()
        value = re.sub(r'[\(\)\[\]\{\}\.\,\-\_\/\\\!\?\']', ' ', value)
        value = re.sub(r'\s+', ' ', value)
        return value.strip()

    def _fetch_discogs_links(self, release_id: Optional[int]) -> Dict[str, Optional[str]]:
        if not release_id:
            return {}
        if release_id in self.discogs_cache:
            return self.discogs_cache[release_id]
        
        result = {}
        try:
            response = self.session.get(
                f"https://api.discogs.com/releases/{release_id}",
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                videos = data.get('videos') or []
                youtube_url = None
                for video in videos:
                    uri = video.get('uri')
                    if uri and ('youtube.com' in uri or 'youtu.be' in uri):
                        youtube_url = uri
                        break
                urls = data.get('urls') or []
                bandcamp_url = None
                for url in urls:
                    if 'bandcamp.com' in url.lower():
                        bandcamp_url = url
                        break
                result = {
                    'youtube_url': youtube_url,
                    'bandcamp_url': bandcamp_url
                }
        except Exception as exc:
            logger.debug(f"Discogs lookup failed for release {release_id}: {exc}")
            result = {}
        
        self.discogs_cache[release_id] = result
        return result

    def _search_deezer_preview(self, title: str, artist: str) -> Dict[str, Optional[str]]:
        cache_key = f"{artist}|{title}".lower()
        if cache_key in self.deezer_cache:
            return self.deezer_cache[cache_key]
        
        result = {'preview_url': None, 'deezer_url': None}
        query = f'artist:"{artist}" track:"{title}"'
        try:
            response = self.session.get(
                f"https://api.deezer.com/search?q={quote(query)}",
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                items = data.get('data') or []
                norm_title = self._normalize_text(title)
                norm_artist = self._normalize_text(artist)
                for item in items[:5]:
                    preview = item.get('preview')
                    link = item.get('link')
                    item_title = self._normalize_text(item.get('title'))
                    item_artist = self._normalize_text(item.get('artist', {}).get('name', ''))
                    if preview and not result['preview_url']:
                        result['preview_url'] = preview
                    if link and not result['deezer_url']:
                        result['deezer_url'] = link
                    if norm_title and norm_title in item_title and norm_artist and norm_artist in item_artist:
                        if preview:
                            result['preview_url'] = preview
                        if link:
                            result['deezer_url'] = link
                        break
        except Exception as exc:
            logger.debug(f"Deezer lookup failed for {artist} - {title}: {exc}")
        
        self.deezer_cache[cache_key] = result
        return result

    def _search_youtube_link(self, title: str, artist: str) -> Optional[str]:
        cache_key = f"{artist}|{title}".lower()
        if cache_key in self.youtube_cache:
            return self.youtube_cache[cache_key]
        
        youtube_url = None
        query = quote(f"{artist} {title}")
        try:
            response = self.session.get(
                f"https://piped.video/api/v1/search?q={query}&filter=music_songs",
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                for item in data[:5]:
                    url = item.get('url')
                    if not url:
                        continue
                    if url.startswith('/watch'):
                        youtube_url = f"https://www.youtube.com{url}"
                    else:
                        youtube_url = url
                    if youtube_url:
                        break
        except Exception as exc:
            logger.debug(f"YouTube search failed for {artist} - {title}: {exc}")
        
        self.youtube_cache[cache_key] = youtube_url
        return youtube_url

    def _enrich_external_links(self, track_id: int, track: Dict, existing_links: Dict[str, Optional[str]]):
        updates: Dict[str, Optional[str]] = {}

        discogs_links = self._fetch_discogs_links(track.get('discogs_id'))
        if discogs_links:
            if discogs_links.get('bandcamp_url') and not existing_links.get('bandcamp_url'):
                updates['bandcamp_url'] = discogs_links['bandcamp_url']
            if discogs_links.get('youtube_url') and not existing_links.get('youtube_url'):
                updates['youtube_url'] = discogs_links['youtube_url']

        deezer_links = self._search_deezer_preview(track['title'], track['artist'])
        if deezer_links.get('preview_url') and not existing_links.get('preview_url'):
            updates['preview_url'] = deezer_links['preview_url']
        if deezer_links.get('deezer_url') and not existing_links.get('deezer_url'):
            updates['deezer_url'] = deezer_links['deezer_url']

        if not updates.get('youtube_url') and not existing_links.get('youtube_url'):
            youtube_link = self._search_youtube_link(track['title'], track['artist'])
            if youtube_link:
                updates['youtube_url'] = youtube_link

        if updates:
            set_clause = ", ".join([f"{key} = %({key})s" for key in updates.keys()])
            updates['track_id'] = track_id
            self.cursor.execute(
                f"UPDATE tracks SET {set_clause}, updated_at = NOW() WHERE id = %(track_id)s",
                updates
            )
    
    def _save_track(self, track: Dict) -> bool:
        """Save track to database"""
        try:
            # Check if track already exists
            self.cursor.execute("""
                INSERT INTO tracks (
                    title, artist, album, year, label, 
                    musicbrainz_id, musicbrainz_release_id,
                    duration_sec, tags,
                    bandcamp_url, youtube_url, deezer_url, discogs_id
                ) VALUES (
                    %(title)s, %(artist)s, %(album)s, %(year)s, %(label)s,
                    %(musicbrainz_id)s, %(musicbrainz_release_id)s,
                    %(duration_sec)s, %(tags)s,
                    %(bandcamp_url)s, %(youtube_url)s, %(deezer_url)s, %(discogs_id)s
                )
                ON CONFLICT (musicbrainz_id) DO UPDATE
                SET
                    title = EXCLUDED.title,
                    artist = EXCLUDED.artist,
                    album = EXCLUDED.album,
                    year = EXCLUDED.year,
                    label = EXCLUDED.label,
                    duration_sec = COALESCE(EXCLUDED.duration_sec, tracks.duration_sec),
                    tags = COALESCE(EXCLUDED.tags, tracks.tags),
                    bandcamp_url = COALESCE(EXCLUDED.bandcamp_url, tracks.bandcamp_url),
                    youtube_url = COALESCE(EXCLUDED.youtube_url, tracks.youtube_url),
                    deezer_url = COALESCE(EXCLUDED.deezer_url, tracks.deezer_url),
                    discogs_id = COALESCE(EXCLUDED.discogs_id, tracks.discogs_id),
                    updated_at = NOW()
                RETURNING id, preview_url, bandcamp_url, youtube_url, deezer_url
            """, track)
            
            record = self.cursor.fetchone()
            if record:
                self._enrich_external_links(record['id'], track, record)
            status = self.cursor.statusmessage or ""
            is_insert = status.startswith('INSERT')
            
            logger.info(f"Saved: {track['artist']} - {track['title']}")
            return is_insert
            
        except psycopg2.Error as e:
            logger.error(f"Database error saving track: {e}")
            self.conn.rollback()
            return False
    
    def close(self):
        """Close database connection"""
        self.cursor.close()
        self.conn.close()


# Underground labels to crawl
UNDERGROUND_LABELS = [
    # Techno
    "Ostgut Ton",
    "Clone Records",
    "Tresor",
    "Planet Mu",
    "Warp Records",
    "R&S Records",
    "Kompakt",
    "Dial Records",
    
    # House
    "Perlon",
    "Ilian Tape",
    "Delsin Records",
    "Lobster Theremin",
    "Shall Not Fade",
    
    # Experimental/IDM
    "Ninja Tune",
    "Hyperdub",
    "PAN",
    "Tri Angle",
    "RVNG Intl.",
    
    # Bass/Dubstep
    "Deep Medi Musik",
    "Tempa",
    "Hessle Audio",
    
    # Drum & Bass/Jungle
    "Metalheadz",
    "Dispatch Recordings",
    "Critical Music",
    
    # Hip-Hop/Beats
    "Stones Throw",
    "Brainfeeder",
    "Def Jux",
    
    # Jazz/Fusion
    "Blue Note",
    "ECM Records",
    "Flying Lotus",
]


if __name__ == "__main__":
    DB_CONFIG = {
        'host': 'localhost',
        'port': 5432,
        'database': 'rebel_music',
        'user': 'rebel',
        'password': 'rebel_password'
    }
    
    crawler = MusicBrainzCrawler(DB_CONFIG)
    
    try:
        # Crawl multiple labels (100 releases each)
        for label in ["Warp Records", "Ninja Tune", "Hyperdub", "Planet Mu"]:
            logger.info(f"\n{'='*60}")
            logger.info(f"Crawling: {label}")
            logger.info(f"{'='*60}\n")
            crawler.crawl_label(label, limit=100)
            time.sleep(2)  # Pause between labels
        
    finally:
        crawler.close()
    
    logger.info("\n✅ Crawl complete!")
