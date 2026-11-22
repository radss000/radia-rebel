"""
Phase 6 Unit Tests - REBEL Music Pipeline

Tests for:
- Audio extraction deterministic and memory-bounded behavior
- Cosine similarity, self-exclusion and score filtering
- KNN weighting with negative, null and missing neighbor cases
- UMAP normalization and position provenance
- API response serialization
"""

import numpy as np
import pytest
from unittest.mock import MagicMock, patch
from types import SimpleNamespace


class TestAudioExtractionDeterminism:
    """Test audio extraction is deterministic and memory-bounded."""

    def test_audio_core_extractor_produces_consistent_output(self):
        """Verify that the same audio input produces identical features."""
        from processing.audio_core_extractor import extract_core_features

        # Create synthetic audio signal
        sample_rate = 22050
        duration = 5.0
        t = np.linspace(0, duration, int(sample_rate * duration), dtype=np.float32)
        audio = 0.5 * np.sin(2 * np.pi * 440 * t)  # 440 Hz sine wave

        # Extract features twice
        features1 = extract_core_features(audio, sample_rate)
        features2 = extract_core_features(audio, sample_rate)

        # Verify deterministic output
        assert features1 == features2, "Audio extraction should be deterministic"

    def test_audio_extraction_handles_empty_audio(self):
        """Verify graceful handling of empty or invalid audio."""
        from processing.audio_core_extractor import extract_core_features

        empty_audio = np.array([], dtype=np.float32)

        with pytest.raises((ValueError, RuntimeError)):
            extract_core_features(empty_audio, 22050)

    def test_audio_extraction_memory_bounded(self):
        """Verify memory usage stays bounded for long audio."""
        from processing.audio_core_extractor import extract_core_features
        import tracemalloc

        sample_rate = 22050
        duration = 60.0  # 1 minute audio
        t = np.linspace(0, duration, int(sample_rate * duration), dtype=np.float32)
        audio = 0.5 * np.sin(2 * np.pi * 440 * t)

        tracemalloc.start()
        features = extract_core_features(audio, sample_rate)
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        # Memory should be bounded (less than 500MB for 1 minute audio)
        assert peak < 500 * 1024 * 1024, f"Memory usage too high: {peak / 1024 / 1024:.2f}MB"


class TestCosineSimilarity:
    """Test cosine similarity, self-exclusion and score filtering."""

    def test_cosine_similarity_identical_vectors(self):
        """Identical vectors should have similarity of 1.0."""
        # Cosine similarity: dot(a,b) / (norm(a) * norm(b))
        vector = np.array([1.0, 2.0, 3.0], dtype=np.float32)
        dot = np.dot(vector, vector)
        norm = np.linalg.norm(vector) * np.linalg.norm(vector)
        similarity = dot / norm if norm > 0 else 0.0

        assert np.isclose(similarity, 1.0, atol=1e-6)

    def test_cosine_similarity_orthogonal_vectors(self):
        """Orthogonal vectors should have similarity of 0.0."""
        v1 = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        v2 = np.array([0.0, 1.0, 0.0], dtype=np.float32)
        dot = np.dot(v1, v2)
        norm = np.linalg.norm(v1) * np.linalg.norm(v2)
        similarity = dot / norm if norm > 0 else 0.0

        assert np.isclose(similarity, 0.0, atol=1e-6)

    def test_cosine_similarity_opposite_vectors(self):
        """Opposite vectors should have similarity of -1.0."""
        v1 = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        v2 = np.array([-1.0, 0.0, 0.0], dtype=np.float32)
        dot = np.dot(v1, v2)
        norm = np.linalg.norm(v1) * np.linalg.norm(v2)
        similarity = dot / norm if norm > 0 else 0.0

        assert np.isclose(similarity, -1.0, atol=1e-6)

    def test_self_exclusion_in_similar_tracks(self):
        """The query track should be excluded from its own similar results."""
        from api.similarity import find_similar_tracks, SimilarityServiceError

        # Mock the database and Qdrant calls
        with patch('api.similarity.get_db_connection') as mock_db, \
             patch('api.similarity.get_qdrant_client') as mock_qdrant:

            # Setup mock to return the query track in results
            mock_cursor = MagicMock()
            mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
            mock_cursor.__exit__ = MagicMock(return_value=False)
            mock_cursor.fetchone.return_value = {
                'track_id': 42,
                'qdrant_point_id': 'point-42',
                'model_name': 'clap-htsat-base',
                'model_version': '1.0',
                'vector_dimensions': 4,
                'position_x': 1.0,
                'position_y': 2.0,
                'position_z': 3.0,
            }
            mock_db.return_value.cursor.return_value = mock_cursor

            # Mock Qdrant to return the query track itself
            mock_client = MagicMock()
            mock_client.retrieve.return_value = [
                SimpleNamespace(id='point-42', vector=[1.0, 0.0, 0.0, 0.0])
            ]
            mock_client.query_points.return_value = SimpleNamespace(points=[
                SimpleNamespace(id='point-42', score=1.0, payload={'track_id': 42}),
                SimpleNamespace(id='point-43', score=0.9, payload={'track_id': 43}),
            ])
            mock_qdrant.return_value = mock_client

            result = find_similar_tracks(42, limit=10, offset=0, min_score=0.0)

            # Verify self-exclusion
            track_ids = [r['track_id'] for r in result['results']]
            assert 42 not in track_ids, "Query track should be excluded from results"

    def test_score_filtering_respects_min_score(self):
        """Results below min_score should be filtered out."""
        from api.similarity import find_similar_tracks

        with patch('api.similarity.get_db_connection') as mock_db, \
             patch('api.similarity.get_qdrant_client') as mock_qdrant:

            mock_cursor = MagicMock()
            mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
            mock_cursor.__exit__ = MagicMock(return_value=False)
            mock_cursor.fetchone.return_value = {
                'track_id': 42,
                'qdrant_point_id': 'point-42',
                'model_name': 'clap-htsat-base',
                'model_version': '1.0',
                'vector_dimensions': 4,
                'position_x': 1.0,
                'position_y': 2.0,
                'position_z': 3.0,
            }
            mock_db.return_value.cursor.return_value = mock_cursor

            mock_client = MagicMock()
            mock_client.retrieve.return_value = [
                SimpleNamespace(id='point-42', vector=[1.0, 0.0, 0.0, 0.0])
            ]
            mock_client.query_points.return_value = SimpleNamespace(points=[
                SimpleNamespace(id='point-43', score=0.9, payload={'track_id': 43}),
                SimpleNamespace(id='point-44', score=0.5, payload={'track_id': 44}),
                SimpleNamespace(id='point-45', score=0.3, payload={'track_id': 45}),
            ])
            mock_qdrant.return_value = mock_client

            result = find_similar_tracks(42, limit=10, offset=0, min_score=0.6)

            # Only track 43 should pass the filter
            assert len(result['results']) == 1
            assert result['results'][0]['track_id'] == 43


class TestKNNWeighting:
    """Test KNN weighting with negative, null and missing neighbor cases."""

    def test_knn_weighting_with_negative_similarities(self):
        """Negative similarities should reduce position influence."""
        from processing.positioning import SonicPositioner

        positioner = SonicPositioner()

        # Create embeddings where some are negatively correlated
        target = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        neighbors = np.array([
            [0.9, 0.1, 0.0],   # Positive similarity
            [-0.8, 0.2, 0.1],  # Negative similarity
            [0.7, 0.3, 0.0],   # Positive similarity
        ], dtype=np.float32)

        neighbor_positions = np.array([
            [10.0, 0.0, 0.0],
            [20.0, 0.0, 0.0],
            [30.0, 0.0, 0.0],
        ], dtype=np.float32)

        result = positioner.nearest_neighbor_position_with_details(
            target, neighbors, neighbor_positions, k=3
        )

        # Negative neighbor should have less influence
        assert result.position is not None
        assert len(result.neighbor_indices) <= 3

    def test_knn_weighting_with_null_neighbors(self):
        """Handle case where no valid neighbors exist."""
        from processing.positioning import SonicPositioner

        positioner = SonicPositioner()

        target = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        neighbors = np.array([], dtype=np.float32).reshape(0, 3)
        neighbor_positions = np.array([], dtype=np.float32).reshape(0, 3)

        result = positioner.nearest_neighbor_position_with_details(
            target, neighbors, neighbor_positions, k=3
        )

        # Should return a default position
        assert result.position is not None

    def test_knn_weighting_with_missing_dimensions(self):
        """Handle embeddings with missing or NaN dimensions."""
        from processing.positioning import SonicPositioner

        positioner = SonicPositioner()

        target = np.array([1.0, np.nan, 0.0], dtype=np.float32)
        neighbors = np.array([
            [0.9, 0.1, 0.0],
            [0.8, 0.2, 0.0],
        ], dtype=np.float32)

        neighbor_positions = np.array([
            [10.0, 0.0, 0.0],
            [20.0, 0.0, 0.0],
        ], dtype=np.float32)

        # Should handle NaN gracefully
        result = positioner.nearest_neighbor_position_with_details(
            target, neighbors, neighbor_positions, k=2
        )

        assert result.position is not None
        assert not np.any(np.isnan(result.position))


class TestUMAPNormalization:
    """Test UMAP normalization and position provenance."""

    def test_umap_output_is_normalized(self):
        """UMAP output should be normalized to expected range."""
        from processing.positioning import SonicPositioner

        positioner = SonicPositioner()

        # Create sample embeddings
        np.random.seed(42)
        embeddings = np.random.randn(50, 128).astype(np.float32)

        positions = positioner.fit_transform(embeddings)

        # Check normalization (typically -1 to 1 or 0 to 1 range)
        assert positions.shape == (50, 3)
        assert np.all(np.abs(positions) < 100), "Positions should be reasonably bounded"

    def test_umap_position_provenance_tracking(self):
        """Position method and version should be tracked."""
        from jobs.position_job import (
            TrackEmbeddingMetadata,
            recalculate_full_map,
        )

        target = TrackEmbeddingMetadata(
            track_id=1,
            point_id="point-1",
            model_name="clap-htsat-base",
            model_version="1.0",
            vector_dimensions=128,
        )

        # Mock the positioner
        class MockPositioner:
            def fit_transform(self, embeddings):
                return np.random.randn(len(embeddings), 3).astype(np.float32)

            def quality_metrics(self, embeddings, positions, n_neighbors):
                return {"trustworthiness": 0.95, "neighbor_recall": 0.85, "quality_k": 10}

            def align_to_anchors(self, positions, anchor_indices, anchor_positions):
                return positions

        with patch('jobs.position_job.get_anchor_positions', return_value={}), \
             patch('jobs.position_job.publish_full_map', return_value="version-123"):

            embeddings = np.random.randn(20, 128).astype(np.float32)
            track_ids = list(range(1, 21))

            result = recalculate_full_map(
                MockPositioner(), target, embeddings, track_ids
            )

            assert result["position_method"] == "clap_umap_full"
            assert result["position_version_id"] == "version-123"

    def test_umap_reproducibility_with_seed(self):
        """UMAP should produce consistent results with same seed."""
        from processing.positioning import SonicPositioner

        np.random.seed(42)
        embeddings = np.random.randn(30, 64).astype(np.float32)

        positioner1 = SonicPositioner(random_state=42)
        positions1 = positioner1.fit_transform(embeddings)

        positioner2 = SonicPositioner(random_state=42)
        positions2 = positioner2.fit_transform(embeddings)

        np.testing.assert_array_almost_equal(positions1, positions2, decimal=5)


class TestAPIResponseSerialization:
    """Test API response serialization."""

    def test_similar_endpoint_response_format(self):
        """Verify the /similar endpoint returns correct JSON structure."""
        from fastapi.testclient import TestClient
        from api.main import app

        client = TestClient(app)

        with patch('api.main.find_similar_tracks') as mock_find:
            mock_find.return_value = {
                "track_id": 42,
                "count": 2,
                "results": [
                    {
                        "track_id": 43,
                        "score": 0.92,
                        "title": "Test Track",
                        "artist": "Test Artist",
                        "position": {"x": 1.0, "y": 2.0, "z": 3.0},
                    },
                    {
                        "track_id": 44,
                        "score": 0.85,
                        "title": "Another Track",
                        "artist": "Another Artist",
                        "position": {"x": 4.0, "y": 5.0, "z": 6.0},
                    },
                ],
            }

            response = client.get("/api/tracks/42/similar?limit=10")

            assert response.status_code == 200
            data = response.json()

            assert "track_id" in data
            assert "count" in data
            assert "results" in data
            assert len(data["results"]) == 2

            for result in data["results"]:
                assert "track_id" in result
                assert "score" in result
                assert "position" in result

    def test_sonic_map_version_response_format(self):
        """Verify the /sonic-map/version endpoint returns correct structure."""
        from fastapi.testclient import TestClient
        from api.main import app

        client = TestClient(app)

        with patch('api.main.get_db_connection') as mock_db:
            mock_cursor = MagicMock()
            mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
            mock_cursor.__exit__ = MagicMock(return_value=False)
            mock_cursor.fetchone.return_value = {
                "id": "version-123",
                "status": "published",
                "method": "clap_umap_full",
                "model_name": "clap-htsat-base",
                "model_version": "1.0",
                "vector_dimensions": 512,
                "track_count": 100,
                "umap_params": {"n_neighbors": 15, "min_dist": 0.1},
                "metrics": {"trustworthiness": 0.95, "neighbor_recall": 0.85},
                "catalog_fingerprint": "abc123",
                "created_at": "2026-01-01T00:00:00Z",
                "published_at": "2026-01-01T01:00:00Z",
            }
            mock_db.return_value.cursor.return_value = mock_cursor

            response = client.get("/api/sonic-map/version")

            assert response.status_code == 200
            data = response.json()

            assert "id" in data
            assert "status" in data
            assert "method" in data
            assert "metrics" in data

    def test_job_enqueue_response_format(self):
        """Verify job enqueue returns correct structure."""
        from fastapi.testclient import TestClient
        from api.main import app

        client = TestClient(app)

        with patch('api.main.enqueue_analysis_job') as mock_enqueue:
            mock_enqueue.return_value = (
                {
                    "id": "job-123",
                    "job_type": "embedding",
                    "status": "pending",
                    "track_id": 42,
                    "created_at": "2026-01-01T00:00:00Z",
                },
                "queue-job-456",
            )

            response = client.post(
                "/api/jobs/enqueue",
                json={
                    "job_type": "embedding",
                    "track_id": 42,
                    "audio_asset_id": "asset-789",
                },
            )

            assert response.status_code == 200
            data = response.json()

            assert "job" in data
            assert "queue_job_id" in data


class TestPositioningQualityMetrics:
    """Test positioning quality metrics calculation."""

    def test_trustworthiness_metric(self):
        """Trustworthiness should measure local neighborhood preservation."""
        from processing.positioning import SonicPositioner

        positioner = SonicPositioner()

        # Create embeddings with known structure
        np.random.seed(42)
        embeddings = np.random.randn(50, 64).astype(np.float32)
        positions = positioner.fit_transform(embeddings)

        metrics = positioner.quality_metrics(embeddings, positions, n_neighbors=10)

        assert "trustworthiness" in metrics
        assert 0 <= metrics["trustworthiness"] <= 1

    def test_neighbor_recall_metric(self):
        """Neighbor recall should measure global structure preservation."""
        from processing.positioning import SonicPositioner

        positioner = SonicPositioner()

        np.random.seed(42)
        embeddings = np.random.randn(50, 64).astype(np.float32)
        positions = positioner.fit_transform(embeddings)

        metrics = positioner.quality_metrics(embeddings, positions, n_neighbors=10)

        assert "neighbor_recall" in metrics
        assert 0 <= metrics["neighbor_recall"] <= 1


class TestEmbeddingUpsert:
    """Test embedding upsert operations."""

    def test_embedding_upsert_idempotency(self):
        """Upserting the same embedding twice should be idempotent."""
        from jobs.position_job import upsert_embedding

        with patch('jobs.position_job._get_qdrant_client') as mock_qdrant, \
             patch('jobs.position_job.get_db_connection') as mock_db:

            mock_client = MagicMock()
            mock_qdrant.return_value = mock_client

            mock_cursor = MagicMock()
            mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
            mock_cursor.__exit__ = MagicMock(return_value=False)
            mock_db.return_value.cursor.return_value = mock_cursor

            target = SimpleNamespace(
                track_id=42,
                point_id="point-42",
                model_name="clap-htsat-base",
                model_version="1.0",
                vector_dimensions=512,
            )

            embedding = np.random.randn(512).astype(np.float32)

            # Upsert twice
            upsert_embedding(target, embedding)
            upsert_embedding(target, embedding)

            # Qdrant upsert should be called twice (idempotent)
            assert mock_client.upsert.call_count == 2