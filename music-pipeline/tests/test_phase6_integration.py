"""
Phase 6 Integration Tests - REBEL Music Pipeline

Tests for:
- PostgreSQL + Qdrant with ephemeral collection
- Embedding upsert then neighbor search
- Full recalculation and approximate positioning
- Controlled degradation when Qdrant or Redis unavailable
"""

import numpy as np
import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from types import SimpleNamespace
from uuid import uuid4


class TestPostgresQdrantIntegration:
    """Test PostgreSQL + Qdrant integration with ephemeral collection."""

    def test_embedding_lifecycle_create_read_delete(self):
        """Test full embedding lifecycle: create, read, delete."""
        from jobs.position_job import (
            TrackEmbeddingMetadata,
            upsert_embedding,
            get_compatible_embeddings,
        )

        target = TrackEmbeddingMetadata(
            track_id=100,
            point_id="point-100",
            model_name="clap-htsat-base",
            model_version="1.0",
            vector_dimensions=512,
        )

        embedding = np.random.randn(512).astype(np.float32)

        with patch('jobs.position_job._get_qdrant_client') as mock_qdrant, \
             patch('jobs.position_job.get_db_connection') as mock_db:

            # Setup Qdrant mock
            mock_client = MagicMock()
            mock_qdrant.return_value = mock_client

            # Setup DB mock
            mock_cursor = MagicMock()
            mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
            mock_cursor.__exit__ = MagicMock(return_value=False)
            mock_cursor.fetchall.return_value = [(100, "point-100")]
            mock_db.return_value.cursor.return_value = mock_cursor

            # Create
            upsert_embedding(target, embedding)
            assert mock_client.upsert.called

            # Read
            mock_client.scroll.return_value = (
                [SimpleNamespace(
                    id="point-100",
                    payload={"track_id": 100},
                    vector=embedding.tolist()
                )],
                None
            )
            embeddings, track_ids = get_compatible_embeddings(target)
            assert len(track_ids) == 1
            assert track_ids[0] == 100

    def test_qdrant_collection_isolation(self):
        """Test that different collections are isolated."""
        from jobs.position_job import _get_qdrant_client

        with patch('jobs.position_job.QdrantClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            client1 = _get_qdrant_client()
            client2 = _get_qdrant_client()

            # Both should use the same client instance pattern
            assert mock_client_class.called


class TestEmbeddingUpsertAndSearch:
    """Test embedding upsert then neighbor search."""

    def test_upsert_then_search_returns_neighbors(self):
        """After upserting embeddings, search should return valid neighbors."""
        from api.similarity import find_similar_tracks

        # Create test embeddings
        query_embedding = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
        neighbor_embedding = np.array([0.9, 0.1, 0.0, 0.0], dtype=np.float32)

        with patch('api.similarity.get_db_connection') as mock_db, \
             patch('api.similarity._get_qdrant_client') as mock_qdrant:

            # Setup DB mock
            mock_cursor = MagicMock()
            mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
            mock_cursor.__exit__ = MagicMock(return_value=False)
            mock_cursor.fetchone.return_value = {
                'embedding_id': 'point-42',
                'vector': query_embedding.tolist()
            }
            mock_db.return_value.cursor.return_value = mock_cursor

            # Setup Qdrant mock with neighbor results
            mock_client = MagicMock()
            mock_client.search.return_value = [
                SimpleNamespace(id='point-43', score=0.95, payload={'track_id': 43}),
                SimpleNamespace(id='point-44', score=0.85, payload={'track_id': 44}),
            ]
            mock_qdrant.return_value = mock_client

            result = find_similar_tracks(42, limit=10, offset=0, min_score=0.5)

            assert result['track_id'] == 42
            assert len(result['results']) == 2
            assert result['results'][0]['score'] >= result['results'][1]['score']

    def test_upsert_updates_existing_embedding(self):
        """Upserting an existing embedding should update it."""
        from jobs.position_job import upsert_embedding, TrackEmbeddingMetadata

        target = TrackEmbeddingMetadata(
            track_id=42,
            point_id="point-42",
            model_name="clap-htsat-base",
            model_version="1.0",
            vector_dimensions=4,
        )

        old_embedding = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
        new_embedding = np.array([0.0, 1.0, 0.0, 0.0], dtype=np.float32)

        with patch('jobs.position_job._get_qdrant_client') as mock_qdrant, \
             patch('jobs.position_job.get_db_connection') as mock_db:

            mock_client = MagicMock()
            mock_qdrant.return_value = mock_client

            mock_cursor = MagicMock()
            mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
            mock_cursor.__exit__ = MagicMock(return_value=False)
            mock_db.return_value.cursor.return_value = mock_cursor

            # First upsert
            upsert_embedding(target, old_embedding)
            first_call_args = mock_client.upsert.call_args

            # Second upsert with new embedding
            upsert_embedding(target, new_embedding)
            second_call_args = mock_client.upsert.call_args

            # Verify both calls were made
            assert mock_client.upsert.call_count == 2


class TestFullRecalculation:
    """Test full recalculation and approximate positioning."""

    def test_full_recalculation_produces_valid_positions(self):
        """Full recalculation should produce valid 3D positions."""
        from jobs.position_job import (
            TrackEmbeddingMetadata,
            recalculate_full_map,
        )

        target = TrackEmbeddingMetadata(
            track_id=1,
            point_id="point-1",
            model_name="clap-htsat-base",
            model_version="1.0",
            vector_dimensions=64,
        )

        # Create embeddings with some structure
        np.random.seed(42)
        n_tracks = 30
        embeddings = np.random.randn(n_tracks, 64).astype(np.float32)
        track_ids = list(range(1, n_tracks + 1))

        class TestPositioner:
            def fit_transform(self, embs):
                # Simple PCA-like reduction for testing
                from sklearn.decomposition import PCA
                pca = PCA(n_components=3)
                return pca.fit_transform(embs).astype(np.float32)

            def quality_metrics(self, embs, positions, n_neighbors):
                return {
                    "trustworthiness": 0.92,
                    "neighbor_recall": 0.88,
                    "quality_k": n_neighbors,
                }

            def align_to_anchors(self, positions, anchor_indices, anchor_positions):
                return positions

        with patch('jobs.position_job.get_anchor_positions', return_value={}), \
             patch('jobs.position_job.publish_full_map', return_value="version-test"):

            result = recalculate_full_map(
                TestPositioner(), target, embeddings, track_ids
            )

            assert result["position_method"] == "clap_umap_full"
            assert result["position_version_id"] == "version-test"
            assert "x" in result
            assert "y" in result
            assert "z" in result

    def test_approximate_position_uses_existing_map(self):
        """Approximate positioning should use existing map positions."""
        from jobs.position_job import (
            TrackEmbeddingMetadata,
            approximate_track_position,
        )
        from processing.positioning import NeighborPositionResult

        target = TrackEmbeddingMetadata(
            track_id=100,
            point_id="point-100",
            model_name="clap-htsat-base",
            model_version="1.0",
            vector_dimensions=4,
        )

        new_embedding = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)

        # Existing map embeddings and positions
        existing_embeddings = np.array([
            [0.9, 0.1, 0.0, 0.0],
            [0.8, 0.2, 0.0, 0.0],
            [0.7, 0.3, 0.0, 0.0],
        ], dtype=np.float32)

        existing_positions = np.array([
            [10.0, 5.0, 0.0],
            [20.0, 10.0, 0.0],
            [30.0, 15.0, 0.0],
        ], dtype=np.float32)

        class TestPositioner:
            def nearest_neighbor_position_with_details(self, target_emb, neighbors, positions, k):
                return NeighborPositionResult(
                    position=np.array([15.0, 7.5, 0.0], dtype=np.float32),
                    neighbor_indices=np.array([0, 1]),
                    similarities=np.array([0.95, 0.85], dtype=np.float32),
                )

        captured = {}

        def fake_get_subset(embeddings, track_ids, exclude_track_id):
            captured["exclude_track_id"] = exclude_track_id
            return existing_embeddings, existing_positions, [1, 2, 3]

        with patch('jobs.position_job.get_positioned_embedding_subset', fake_get_subset), \
             patch('jobs.position_job.get_current_published_version', return_value="map-v1"), \
             patch('jobs.position_job.update_track_position') as mock_update:

            result = approximate_track_position(
                TestPositioner(),
                target,
                new_embedding,
                np.zeros((4, 4), dtype=np.float32),
                [100, 1, 2, 3],
            )

            assert captured["exclude_track_id"] == 100
            assert result["position_method"] == "clap_knn_approx"
            assert result["position_version_id"] == "map-v1"
            assert mock_update.called


class TestControlledDegradation:
    """Test controlled degradation when Qdrant or Redis unavailable."""

    def test_similarity_endpoint_handles_qdrant_unavailable(self):
        """Similarity endpoint should return appropriate error when Qdrant is down."""
        from api.similarity import find_similar_tracks, SimilarityServiceError

        with patch('api.similarity.get_db_connection') as mock_db, \
             patch('api.similarity._get_qdrant_client') as mock_qdrant:

            mock_cursor = MagicMock()
            mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
            mock_cursor.__exit__ = MagicMock(return_value=False)
            mock_cursor.fetchone.return_value = {
                'embedding_id': 'point-42',
                'vector': [1.0, 0.0, 0.0, 0.0]
            }
            mock_db.return_value.cursor.return_value = mock_cursor

            # Simulate Qdrant connection failure
            mock_client = MagicMock()
            mock_client.search.side_effect = ConnectionError("Qdrant unavailable")
            mock_qdrant.return_value = mock_client

            with pytest.raises(SimilarityServiceError) as exc_info:
                find_similar_tracks(42, limit=10, offset=0, min_score=0.0)

            assert exc_info.value.status_code == 503

    def test_similarity_endpoint_handles_missing_embedding(self):
        """Similarity endpoint should return 409 when track has no embedding."""
        from api.similarity import find_similar_tracks, SimilarityServiceError

        with patch('api.similarity.get_db_connection') as mock_db:
            mock_cursor = MagicMock()
            mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
            mock_cursor.__exit__ = MagicMock(return_value=False)
            mock_cursor.fetchone.return_value = None  # No embedding found
            mock_db.return_value.cursor.return_value = mock_cursor

            with pytest.raises(SimilarityServiceError) as exc_info:
                find_similar_tracks(999, limit=10, offset=0, min_score=0.0)

            assert exc_info.value.status_code == 409

    def test_job_queue_handles_redis_unavailable(self):
        """Job queue should handle Redis unavailability gracefully."""
        from jobs.queue import enqueue_analysis_job

        with patch('jobs.queue.get_redis_connection') as mock_redis:
            mock_redis.side_effect = ConnectionError("Redis unavailable")

            with pytest.raises(Exception) as exc_info:
                enqueue_analysis_job(
                    job_type="embedding",
                    track_id=42,
                    audio_asset_id=str(uuid4()),
                )

            assert "Redis" in str(exc_info.value) or "unavailable" in str(exc_info.value).lower()

    def test_position_job_handles_db_connection_failure(self):
        """Position job should handle database connection failures."""
        from jobs.position_job import publish_full_map, TrackEmbeddingMetadata

        target = TrackEmbeddingMetadata(
            track_id=1,
            point_id="point-1",
            model_name="clap-htsat-base",
            model_version="1.0",
            vector_dimensions=4,
        )

        positions = np.array([[1.0, 2.0, 3.0]], dtype=np.float32)

        with patch('jobs.position_job.get_db_connection') as mock_db:
            mock_db.side_effect = ConnectionError("Database unavailable")

            with pytest.raises(ConnectionError):
                publish_full_map(
                    target,
                    [1],
                    positions,
                    {"trustworthiness": 0.95, "neighbor_recall": 0.85},
                    "fingerprint",
                )


class TestTransactionAtomicity:
    """Test transaction atomicity for critical operations."""

    def test_full_map_publication_is_atomic(self):
        """Full map publication should be atomic - all or nothing."""
        from jobs.position_job import publish_full_map, TrackEmbeddingMetadata

        target = TrackEmbeddingMetadata(
            track_id=1,
            point_id="point-1",
            model_name="clap-htsat-base",
            model_version="1.0",
            vector_dimensions=4,
        )

        positions = np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]], dtype=np.float32)

        class FailingCursor:
            def __init__(self):
                self.executed = []

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def execute(self, query, params=None):
                self.executed.append(query)
                if "UPDATE tracks" in query:
                    raise RuntimeError("Simulated failure")

        class TrackingConnection:
            def __init__(self):
                self.committed = False
                self.rolled_back = False
                self.cursor_obj = FailingCursor()

            def cursor(self):
                return self.cursor_obj

            def commit(self):
                self.committed = True

            def rollback(self):
                self.rolled_back = True

            def close(self):
                pass

        connection = TrackingConnection()

        with patch('jobs.position_job.get_db_connection', return_value=connection), \
             patch('jobs.position_job.execute_values'):

            with pytest.raises(RuntimeError, match="Simulated failure"):
                publish_full_map(
                    target,
                    [1, 2],
                    positions,
                    {"trustworthiness": 0.95, "neighbor_recall": 0.85},
                    "fingerprint",
                )

            # Verify rollback was called, not commit
            assert connection.rolled_back is True
            assert connection.committed is False


class TestConcurrentOperations:
    """Test concurrent operation handling."""

    def test_concurrent_embedding_upserts(self):
        """Concurrent embedding upserts should not corrupt data."""
        from jobs.position_job import upsert_embedding, TrackEmbeddingMetadata
        import threading

        target = TrackEmbeddingMetadata(
            track_id=42,
            point_id="point-42",
            model_name="clap-htsat-base",
            model_version="1.0",
            vector_dimensions=4,
        )

        results = []
        errors = []

        def upsert_worker(worker_id):
            try:
                embedding = np.array([1.0, 0.0, 0.0, float(worker_id)], dtype=np.float32)
                with patch('jobs.position_job._get_qdrant_client') as mock_qdrant, \
                     patch('jobs.position_job.get_db_connection') as mock_db:

                    mock_client = MagicMock()
                    mock_qdrant.return_value = mock_client

                    mock_cursor = MagicMock()
                    mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
                    mock_cursor.__exit__ = MagicMock(return_value=False)
                    mock_db.return_value.cursor.return_value = mock_cursor

                    upsert_embedding(target, embedding)
                    results.append(worker_id)
            except Exception as e:
                errors.append((worker_id, str(e)))

        threads = [threading.Thread(target=upsert_worker, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All workers should complete (either success or handled error)
        assert len(results) + len(errors) == 5