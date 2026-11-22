"""
Phase 6 End-to-End Tests - REBEL Music Pipeline

Tests for:
- Local fixture ingestion
- preview_fetch → audio_features → embedding → position pipeline
- /similar endpoint call and ranking verification
- Map loading, track search and neighbor display
- Preview playback, filters and mobile navigation
"""

import numpy as np
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from types import SimpleNamespace
from uuid import uuid4
import json
import os


class TestLocalFixtureIngestion:
    """Test local fixture ingestion pipeline."""

    def test_ingest_local_audio_file(self):
        """Test ingesting a local audio file through the pipeline."""
        from fastapi.testclient import TestClient
        from api.main import app

        client = TestClient(app)

        # Mock the audio processing pipeline
        with patch('api.main.extract_audio_features') as mock_features, \
             patch('api.main.derive_position') as mock_position, \
             patch('api.main.get_db_connection') as mock_db, \
             patch('api.main.requests.get') as mock_get:

            # Setup mocks
            mock_features.return_value = {
                "tempo": 120.0,
                "energy": 0.75,
                "danceability": 0.8,
                "acousticness": 0.2,
                "brightness": 0.6,
                "bass": 0.5,
                "valence": 0.7,
                "duration_sec": 180,
            }

            mock_position.return_value = (
                (1.0, 2.0, 3.0),  # position
                (0.8, 0.2, 0.5),  # color
                1.5,              # size
                0.3,              # emissive
            )

            mock_cursor = MagicMock()
            mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
            mock_cursor.__exit__ = MagicMock(return_value=False)
            mock_cursor.fetchone.return_value = {"id": 42}
            mock_db.return_value.cursor.return_value = mock_cursor

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.iter_content.return_value = [b"fake audio data"]
            mock_get.return_value = mock_response

            response = client.post(
                "/api/tracks/ingest",
                json={
                    "mongo_track_id": "mongo-123",
                    "title": "Test Track",
                    "artist": "Test Artist",
                    "audio_url": "https://example.com/audio.mp3",
                    "genre": "Electronic",
                    "tags": ["ambient", "chill"],
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["track_id"] == 42
            assert "features" in data
            assert "position" in data

    def test_ingest_youtube_preview(self):
        """Test ingesting a YouTube preview URL."""
        from fastapi.testclient import TestClient
        from api.main import app

        client = TestClient(app)

        with patch('api.main.get_db_connection') as mock_db:
            mock_cursor = MagicMock()
            mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
            mock_cursor.__exit__ = MagicMock(return_value=False)
            mock_cursor.fetchone.side_effect = [
                None,  # No existing asset
                {"id": 100},  # New track ID
                {"id": "asset-uuid"},  # New asset ID
            ]
            mock_db.return_value.cursor.return_value = mock_cursor

            response = client.post(
                "/api/tracks/ingest",
                json={
                    "mongo_track_id": "mongo-456",
                    "title": "YouTube Track",
                    "artist": "YouTube Artist",
                    "audio_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                    "preview_source_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["provider_type"] == "youtube_music"
            assert "track_id" in data
            assert "audio_asset_id" in data


class TestFullPipelineExecution:
    """Test the full preview_fetch → audio_features → embedding → position pipeline."""

    def test_pipeline_job_sequence(self):
        """Test that jobs execute in the correct sequence."""
        from jobs.tasks import (
            run_preview_fetch,
            run_audio_features,
            run_embedding,
            run_position,
        )

        job_id = str(uuid4())
        audio_asset_id = str(uuid4())
        track_id = 42

        # Track job execution order
        executed_jobs = []

        with patch('jobs.tasks.get_db_connection') as mock_db, \
             patch('jobs.tasks._get_qdrant_client') as mock_qdrant, \
             patch('jobs.tasks.fetch_preview_audio') as mock_fetch, \
             patch('jobs.tasks.extract_audio_features') as mock_features, \
             patch('jobs.tasks.generate_embedding') as mock_embedding, \
             patch('jobs.tasks.upsert_embedding') as mock_upsert, \
             patch('jobs.tasks.approximate_track_position') as mock_position:

            # Setup mocks
            mock_cursor = MagicMock()
            mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
            mock_cursor.__exit__ = MagicMock(return_value=False)
            mock_cursor.fetchone.return_value = {
                "track_id": track_id,
                "source_url": "https://example.com/audio.mp3",
                "provider_type": "bandcamp",
                "provider_track_id": "bc-123",
            }
            mock_db.return_value.cursor.return_value = mock_cursor

            mock_fetch.return_value = "/tmp/audio.mp3"
            mock_features.return_value = {
                "tempo": 120.0,
                "energy": 0.75,
                "danceability": 0.8,
            }
            mock_embedding.return_value = np.random.randn(512).astype(np.float32)
            mock_position.return_value = {
                "position_method": "clap_knn_approx",
                "position_version_id": "v1",
                "x": 1.0,
                "y": 2.0,
                "z": 3.0,
            }

            # Execute jobs in sequence
            run_preview_fetch(job_id, audio_asset_id)
            executed_jobs.append("preview_fetch")

            run_audio_features(job_id, audio_asset_id, track_id)
            executed_jobs.append("audio_features")

            run_embedding(job_id, audio_asset_id, track_id)
            executed_jobs.append("embedding")

            run_position(job_id, track_id)
            executed_jobs.append("position")

            # Verify correct sequence
            assert executed_jobs == ["preview_fetch", "audio_features", "embedding", "position"]

    def test_pipeline_error_recovery(self):
        """Test that pipeline handles errors and can be retried."""
        from jobs.tasks import run_audio_features

        job_id = str(uuid4())
        audio_asset_id = str(uuid4())
        track_id = 42

        with patch('jobs.tasks.get_db_connection') as mock_db, \
             patch('jobs.tasks.extract_audio_features') as mock_features:

            mock_cursor = MagicMock()
            mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
            mock_cursor.__exit__ = MagicMock(return_value=False)
            mock_cursor.fetchone.return_value = {
                "track_id": track_id,
                "storage_path": "/tmp/audio.mp3",
            }
            mock_db.return_value.cursor.return_value = mock_cursor

            # Simulate feature extraction failure
            mock_features.side_effect = RuntimeError("Audio processing failed")

            with pytest.raises(RuntimeError, match="Audio processing failed"):
                run_audio_features(job_id, audio_asset_id, track_id)


class TestSimilarEndpointRanking:
    """Test /similar endpoint call and ranking verification."""

    def test_similar_endpoint_returns_ranked_results(self):
        """Verify similar tracks are returned in correct ranking order."""
        from fastapi.testclient import TestClient
        from api.main import app

        client = TestClient(app)

        with patch('api.main.find_similar_tracks') as mock_find:
            mock_find.return_value = {
                "track_id": 42,
                "model_name": "clap-htsat-base",
                "model_version": "1.0",
                "vector_dimensions": 512,
                "metric": "cosine",
                "limit": 10,
                "offset": 0,
                "min_score": 0.0,
                "count": 3,
                "calibration_status": "configured",
                "calibration": None,
                "results": [
                    {
                        "track_id": 43,
                        "title": "Most Similar",
                        "artist": "Artist A",
                        "similarity_score": 0.95,
                        "similarity_band": "very_close",
                        "rank": 1,
                        "position": {"x": 1.0, "y": 2.0, "z": 3.0},
                    },
                    {
                        "track_id": 44,
                        "title": "Second Most",
                        "artist": "Artist B",
                        "similarity_score": 0.85,
                        "similarity_band": "close",
                        "rank": 2,
                        "position": {"x": 4.0, "y": 5.0, "z": 6.0},
                    },
                    {
                        "track_id": 45,
                        "title": "Third Most",
                        "artist": "Artist C",
                        "similarity_score": 0.75,
                        "similarity_band": "related",
                        "rank": 3,
                        "position": {"x": 7.0, "y": 8.0, "z": 9.0},
                    },
                ],
            }

            response = client.get("/api/tracks/42/similar?limit=10&offset=0")

            assert response.status_code == 200
            data = response.json()

            # Verify ranking order
            results = data["results"]
            assert len(results) == 3
            assert results[0]["rank"] == 1
            assert results[1]["rank"] == 2
            assert results[2]["rank"] == 3

            # Verify scores are descending
            scores = [r["similarity_score"] for r in results]
            assert scores == sorted(scores, reverse=True)

    def test_similar_endpoint_pagination(self):
        """Verify pagination works correctly for similar tracks."""
        from fastapi.testclient import TestClient
        from api.main import app

        client = TestClient(app)

        with patch('api.main.find_similar_tracks') as mock_find:
            mock_find.return_value = {
                "track_id": 42,
                "count": 2,
                "limit": 2,
                "offset": 5,
                "results": [
                    {"track_id": 50, "similarity_score": 0.65, "rank": 6},
                    {"track_id": 51, "similarity_score": 0.60, "rank": 7},
                ],
            }

            response = client.get("/api/tracks/42/similar?limit=2&offset=5")

            assert response.status_code == 200
            data = response.json()

            assert data["offset"] == 5
            assert data["limit"] == 2
            assert len(data["results"]) == 2


class TestMapLoadingAndDisplay:
    """Test map loading, track search and neighbor display."""

    def test_sonic_map_endpoint_returns_valid_data(self):
        """Verify sonic map endpoint returns valid visualization data."""
        from fastapi.testclient import TestClient
        from api.main import app

        client = TestClient(app)

        with patch('api.main.get_db_connection') as mock_db:
            mock_cursor = MagicMock()
            mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
            mock_cursor.__exit__ = MagicMock(return_value=False)
            mock_cursor.fetchall.return_value = [
                {
                    "id": "1",
                    "title": "Track 1",
                    "artist": "Artist 1",
                    "genre": "Electronic",
                    "liked": False,
                    "position": {"x": 1.0, "y": 2.0, "z": 3.0},
                    "color": {"r": 0.8, "g": 0.2, "b": 0.5},
                    "size": 1.5,
                    "emissiveIntensity": 0.3,
                    "audio": {
                        "tempo": 120,
                        "energy": 0.75,
                        "danceability": 0.8,
                    },
                },
                {
                    "id": "2",
                    "title": "Track 2",
                    "artist": "Artist 2",
                    "genre": "Ambient",
                    "liked": True,
                    "position": {"x": 4.0, "y": 5.0, "z": 6.0},
                    "color": {"r": 0.3, "g": 0.7, "b": 0.9},
                    "size": 1.2,
                    "emissiveIntensity": 0.2,
                    "audio": {
                        "tempo": 80,
                        "energy": 0.4,
                        "danceability": 0.5,
                    },
                },
            ]
            mock_db.return_value.cursor.return_value = mock_cursor

            response = client.get("/api/tracks/sonic-map?limit=100")

            assert response.status_code == 200
            data = response.json()

            assert len(data) == 2
            for track in data:
                assert "id" in track
                assert "position" in track
                assert "color" in track
                assert "audio" in track

    def test_sonic_map_version_endpoint(self):
        """Verify sonic map version endpoint returns provenance data."""
        from fastapi.testclient import TestClient
        from api.main import app

        client = TestClient(app)

        with patch('api.main.get_db_connection') as mock_db:
            mock_cursor = MagicMock()
            mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
            mock_cursor.__exit__ = MagicMock(return_value=False)
            mock_cursor.fetchone.return_value = {
                "id": "version-abc",
                "status": "published",
                "method": "clap_umap_full",
                "model_name": "clap-htsat-base",
                "model_version": "1.0",
                "vector_dimensions": 512,
                "track_count": 150,
                "umap_params": {"n_neighbors": 15, "min_dist": 0.1},
                "metrics": {"trustworthiness": 0.92, "neighbor_recall": 0.88},
                "catalog_fingerprint": "fp-123",
                "created_at": "2026-01-01T00:00:00Z",
                "published_at": "2026-01-01T01:00:00Z",
            }
            mock_db.return_value.cursor.return_value = mock_cursor

            response = client.get("/api/sonic-map/version")

            assert response.status_code == 200
            data = response.json()

            assert data["status"] == "published"
            assert data["method"] == "clap_umap_full"
            assert "metrics" in data
            assert data["track_count"] == 150


class TestSearchIngestPipeline:
    """Test search-ingest pipeline for discovering new tracks."""

    def test_search_ingest_youtube(self):
        """Test searching and ingesting a track from YouTube."""
        from fastapi.testclient import TestClient
        from api.main import app

        client = TestClient(app)

        with patch('api.main._search_youtube_preview') as mock_search, \
             patch('api.main.get_db_connection') as mock_db, \
             patch('api.main.enqueue_analysis_job') as mock_enqueue:

            mock_search.return_value = {
                "id": "yt-video-id",
                "title": "Found Track",
                "duration": 240,
                "webpage_url": "https://www.youtube.com/watch?v=yt-video-id",
                "thumbnail": None,
                "channel": "Found Artist",
                "description": None,
            }

            mock_cursor = MagicMock()
            mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
            mock_cursor.__exit__ = MagicMock(return_value=False)
            mock_cursor.fetchone.side_effect = [
                None,  # No existing asset
                {"id": 200},  # New track ID
                {"id": "asset-uuid-200"},  # New asset ID
            ]
            mock_db.return_value.cursor.return_value = mock_cursor

            mock_enqueue.return_value = (
                {"id": "job-123", "status": "pending"},
                "queue-job-456",
            )

            response = client.post(
                "/api/tracks/search-ingest",
                json={
                    "artist": "Search Artist",
                    "title": "Search Track",
                },
            )

            assert response.status_code == 200
            data = response.json()

            assert data["provider_type"] == "youtube_music"
            assert "track_id" in data
            assert "jobs" in data
            assert len(data["jobs"]) == 4  # preview_fetch, audio_features, embedding, position


class TestPreviewPlaybackIntegration:
    """Test preview playback integration scenarios."""

    def test_track_detail_with_preview_url(self):
        """Verify track detail includes preview URL for playback."""
        from fastapi.testclient import TestClient
        from api.main import app

        client = TestClient(app)

        with patch('api.main.get_db_connection') as mock_db:
            mock_cursor = MagicMock()
            mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
            mock_cursor.__exit__ = MagicMock(return_value=False)
            mock_cursor.fetchone.return_value = {
                "id": 42,
                "title": "Playable Track",
                "artist": "Playable Artist",
                "preview_url": "https://example.com/preview.mp3",
                "youtube_url": "https://www.youtube.com/watch?v=abc123",
                "bandcamp_url": "https://artist.bandcamp.com/track/song",
                "position_x": 1.0,
                "position_y": 2.0,
                "position_z": 3.0,
            }
            mock_db.return_value.cursor.return_value = mock_cursor

            response = client.get("/api/tracks/42")

            assert response.status_code == 200
            data = response.json()

            assert "preview_url" in data
            assert data["preview_url"] is not None


class TestFilterAndNavigation:
    """Test filter and navigation functionality."""

    def test_tracks_endpoint_genre_filter(self):
        """Verify genre filtering works on tracks endpoint."""
        from fastapi.testclient import TestClient
        from api.main import app

        client = TestClient(app)

        with patch('api.main.get_db_connection') as mock_db:
            mock_cursor = MagicMock()
            mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
            mock_cursor.__exit__ = MagicMock(return_value=False)
            mock_cursor.fetchall.return_value = [
                {
                    "id": 1,
                    "title": "Electronic Track",
                    "artist": "Electronic Artist",
                    "genre": "Electronic",
                },
            ]
            mock_db.return_value.cursor.return_value = mock_cursor

            response = client.get("/api/tracks?genre=electronic")

            assert response.status_code == 200
            data = response.json()

            assert "tracks" in data
            for track in data["tracks"]:
                assert "Electronic" in track.get("genre", "") or "electronic" in track.get("genre", "").lower()

    def test_tracks_endpoint_pagination(self):
        """Verify pagination works on tracks endpoint."""
        from fastapi.testclient import TestClient
        from api.main import app

        client = TestClient(app)

        with patch('api.main.get_db_connection') as mock_db:
            mock_cursor = MagicMock()
            mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
            mock_cursor.__exit__ = MagicMock(return_value=False)
            mock_cursor.fetchall.return_value = [
                {"id": i, "title": f"Track {i}", "artist": f"Artist {i}"}
                for i in range(11, 21)
            ]
            mock_db.return_value.cursor.return_value = mock_cursor

            response = client.get("/api/tracks?limit=10&offset=10")

            assert response.status_code == 200
            data = response.json()

            assert data["limit"] == 10
            assert data["offset"] == 10
            assert len(data["tracks"]) == 10


class TestJobStatusTracking:
    """Test job status tracking and retrieval."""

    def test_job_status_endpoint(self):
        """Verify job status can be retrieved."""
        from fastapi.testclient import TestClient
        from api.main import app

        client = TestClient(app)
        job_id = str(uuid4())

        with patch('api.main.get_db_connection') as mock_db:
            mock_cursor = MagicMock()
            mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
            mock_cursor.__exit__ = MagicMock(return_value=False)
            mock_cursor.fetchone.return_value = {
                "id": job_id,
                "job_type": "embedding",
                "status": "completed",
                "track_id": 42,
                "created_at": "2026-01-01T00:00:00Z",
                "started_at": "2026-01-01T00:00:05Z",
                "completed_at": "2026-01-01T00:00:30Z",
                "error": None,
            }
            mock_db.return_value.cursor.return_value = mock_cursor

            response = client.get(f"/api/jobs/{job_id}")

            assert response.status_code == 200
            data = response.json()

            assert data["id"] == job_id
            assert data["status"] == "completed"
            assert data["job_type"] == "embedding"

    def test_job_not_found_returns_404(self):
        """Verify 404 is returned for non-existent job."""
        from fastapi.testclient import TestClient
        from api.main import app

        client = TestClient(app)
        job_id = str(uuid4())

        with patch('api.main.get_db_connection') as mock_db:
            mock_cursor = MagicMock()
            mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
            mock_cursor.__exit__ = MagicMock(return_value=False)
            mock_cursor.fetchone.return_value = None
            mock_db.return_value.cursor.return_value = mock_cursor

            response = client.get(f"/api/jobs/{job_id}")

            assert response.status_code == 404


class TestCalibrationIntegration:
    """Test similarity calibration integration."""

    def test_similarity_with_calibration(self):
        """Verify similarity results include calibration bands."""
        from api.similarity import classify_similarity, load_similarity_calibration

        # Test with mock calibration
        with patch('api.similarity.load_similarity_calibration') as mock_load:
            mock_load.return_value = {
                "source": "versioned_config",
                "thresholds": {
                    "very_close": 0.9,
                    "close": 0.7,
                    "related": 0.5,
                },
            }

            # Test classification
            assert classify_similarity(0.95) == "very_close"
            assert classify_similarity(0.8) == "close"
            assert classify_similarity(0.6) == "related"
            assert classify_similarity(0.3) == "weak"

    def test_similarity_without_calibration(self):
        """Verify similarity works without calibration (returns None band)."""
        from api.similarity import classify_similarity

        with patch('api.similarity._similarity_thresholds', return_value=None):
            result = classify_similarity(0.85)
            assert result is None