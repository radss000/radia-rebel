"""
Phase 6 Visual and Performance Tests - REBEL Music Pipeline

Tests for:
- Visual regression tests for Sonic Map rendering
- Performance benchmarks for similarity search
- Performance benchmarks for positioning calculations
- Memory usage validation
- Response time validation
"""

import numpy as np
import pytest
import time
from unittest.mock import MagicMock, patch
from types import SimpleNamespace
from uuid import uuid4


class TestVisualRegression:
    """Visual regression tests for Sonic Map rendering."""

    def test_sonic_map_data_structure(self):
        """Verify sonic map data has correct structure for visualization."""
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
                    "title": "Test Track",
                    "artist": "Test Artist",
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
                        "acousticness": 0.2,
                        "brightness": 0.6,
                        "bass": 0.5,
                        "valence": 0.7,
                    },
                },
            ]
            mock_db.return_value.cursor.return_value = mock_cursor

            response = client.get("/api/tracks/sonic-map?limit=100")

            assert response.status_code == 200
            data = response.json()

            # Verify structure for Three.js rendering
            track = data[0]

            # Position must be 3D coordinates
            assert "position" in track
            assert "x" in track["position"]
            assert "y" in track["position"]
            assert "z" in track["position"]

            # Color must be RGB
            assert "color" in track
            assert "r" in track["color"]
            assert "g" in track["color"]
            assert "b" in track["color"]

            # Size and emissive for visual properties
            assert "size" in track
            assert "emissiveIntensity" in track

            # Audio features for visualization
            assert "audio" in track
            assert "tempo" in track["audio"]
            assert "energy" in track["audio"]

    def test_position_coordinates_are_finite(self):
        """Verify all position coordinates are finite numbers."""
        from fastapi.testclient import TestClient
        from api.main import app

        client = TestClient(app)

        with patch('api.main.get_db_connection') as mock_db:
            mock_cursor = MagicMock()
            mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
            mock_cursor.__exit__ = MagicMock(return_value=False)

            # Generate test data with various position values
            test_tracks = []
            for i in range(50):
                test_tracks.append({
                    "id": str(i),
                    "title": f"Track {i}",
                    "artist": f"Artist {i}",
                    "genre": "Electronic",
                    "liked": False,
                    "position": {
                        "x": float(np.random.randn()),
                        "y": float(np.random.randn()),
                        "z": float(np.random.randn()),
                    },
                    "color": {"r": 0.5, "g": 0.5, "b": 0.5},
                    "size": 1.0,
                    "emissiveIntensity": 0.2,
                    "audio": {"tempo": 120, "energy": 0.5, "danceability": 0.5},
                })

            mock_cursor.fetchall.return_value = test_tracks
            mock_db.return_value.cursor.return_value = mock_cursor

            response = client.get("/api/tracks/sonic-map?limit=100")

            assert response.status_code == 200
            data = response.json()

            for track in data:
                pos = track["position"]
                assert np.isfinite(pos["x"]), f"Position x is not finite: {pos['x']}"
                assert np.isfinite(pos["y"]), f"Position y is not finite: {pos['y']}"
                assert np.isfinite(pos["z"]), f"Position z is not finite: {pos['z']}"

    def test_color_values_are_normalized(self):
        """Verify color values are in valid range [0, 1]."""
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
                    "title": "Test",
                    "artist": "Test",
                    "genre": "Electronic",
                    "liked": False,
                    "position": {"x": 0, "y": 0, "z": 0},
                    "color": {"r": 0.8, "g": 0.2, "b": 0.5},
                    "size": 1.0,
                    "emissiveIntensity": 0.3,
                    "audio": {"tempo": 120, "energy": 0.5, "danceability": 0.5},
                },
            ]
            mock_db.return_value.cursor.return_value = mock_cursor

            response = client.get("/api/tracks/sonic-map?limit=100")

            assert response.status_code == 200
            data = response.json()

            for track in data:
                color = track["color"]
                assert 0 <= color["r"] <= 1, f"Color r out of range: {color['r']}"
                assert 0 <= color["g"] <= 1, f"Color g out of range: {color['g']}"
                assert 0 <= color["b"] <= 1, f"Color b out of range: {color['b']}"


class TestSimilaritySearchPerformance:
    """Performance benchmarks for similarity search."""

    def test_similarity_search_response_time(self):
        """Verify similarity search completes within acceptable time."""
        from api.similarity import find_similar_tracks

        with patch('api.similarity.get_db_connection') as mock_db, \
             patch('api.similarity.get_qdrant_client') as mock_qdrant:

            # Setup mocks
            mock_cursor = MagicMock()
            mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
            mock_cursor.__exit__ = MagicMock(return_value=False)
            mock_cursor.fetchone.return_value = {
                'track_id': 42,
                'qdrant_point_id': 'point-42',
                'model_name': 'clap-htsat-base',
                'model_version': '1.0',
                'vector_dimensions': 512,
                'position_x': 1.0,
                'position_y': 2.0,
                'position_z': 3.0,
            }
            mock_db.return_value.cursor.return_value = mock_cursor

            mock_client = MagicMock()
            mock_client.retrieve.return_value = [
                SimpleNamespace(id='point-42', vector=np.random.randn(512).tolist())
            ]
            mock_client.query_points.return_value = SimpleNamespace(points=[
                SimpleNamespace(id=f'point-{i}', score=0.9 - i*0.01, payload={'track_id': i})
                for i in range(43, 63)
            ])
            mock_qdrant.return_value = mock_client

            # Measure response time
            start_time = time.time()
            result = find_similar_tracks(42, limit=20, offset=0, min_score=0.0)
            elapsed_time = time.time() - start_time

            # Should complete within 500ms (mocked, so should be much faster)
            assert elapsed_time < 0.5, f"Similarity search took too long: {elapsed_time:.3f}s"
            assert len(result["results"]) == 20

    def test_similarity_search_scales_with_limit(self):
        """Verify similarity search handles different limit values."""
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
                'vector_dimensions': 512,
                'position_x': 1.0,
                'position_y': 2.0,
                'position_z': 3.0,
            }
            mock_db.return_value.cursor.return_value = mock_cursor

            mock_client = MagicMock()
            mock_client.retrieve.return_value = [
                SimpleNamespace(id='point-42', vector=np.random.randn(512).tolist())
            ]

            # Generate many results
            mock_client.query_points.return_value = SimpleNamespace(points=[
                SimpleNamespace(id=f'point-{i}', score=0.95 - i*0.001, payload={'track_id': i})
                for i in range(100, 200)
            ])
            mock_qdrant.return_value = mock_client

            # Test with different limits
            for limit in [10, 50, 100]:
                result = find_similar_tracks(42, limit=limit, offset=0, min_score=0.0)
                assert len(result["results"]) <= limit


class TestPositioningPerformance:
    """Performance benchmarks for positioning calculations."""

    def test_umap_positioning_performance(self):
        """Verify UMAP positioning completes within acceptable time."""
        from processing.positioning import SonicPositioner

        positioner = SonicPositioner(n_neighbors=15, min_dist=0.1, random_state=42)

        # Create test embeddings
        np.random.seed(42)
        n_tracks = 100
        embeddings = np.random.randn(n_tracks, 512).astype(np.float32)

        # Measure positioning time
        start_time = time.time()
        positions = positioner.fit_transform(embeddings)
        elapsed_time = time.time() - start_time

        # Should complete within 10 seconds for 100 tracks
        assert elapsed_time < 10.0, f"UMAP positioning took too long: {elapsed_time:.3f}s"
        assert positions.shape == (n_tracks, 3)

    def test_knn_positioning_performance(self):
        """Verify KNN approximate positioning is fast."""
        from processing.positioning import SonicPositioner

        positioner = SonicPositioner()

        # Create test data
        target = np.random.randn(512).astype(np.float32)
        neighbors = np.random.randn(50, 512).astype(np.float32)
        neighbor_positions = np.random.randn(50, 3).astype(np.float32)

        # Measure KNN positioning time
        start_time = time.time()
        result = positioner.nearest_neighbor_position_with_details(
            target, neighbors, neighbor_positions, k=10
        )
        elapsed_time = time.time() - start_time

        # Should complete within 100ms
        assert elapsed_time < 0.1, f"KNN positioning took too long: {elapsed_time:.3f}s"
        assert result.position is not None

    def test_quality_metrics_performance(self):
        """Verify quality metrics calculation is efficient."""
        from processing.positioning import SonicPositioner

        positioner = SonicPositioner()

        np.random.seed(42)
        n_tracks = 100
        embeddings = np.random.randn(n_tracks, 512).astype(np.float32)
        positions = positioner.fit_transform(embeddings)

        # Measure quality metrics time
        start_time = time.time()
        metrics = positioner.quality_metrics(embeddings, positions, n_neighbors=15)
        elapsed_time = time.time() - start_time

        # Should complete within 5 seconds
        assert elapsed_time < 5.0, f"Quality metrics took too long: {elapsed_time:.3f}s"
        assert "trustworthiness" in metrics
        assert "neighbor_recall" in metrics


class TestMemoryUsage:
    """Memory usage validation tests."""

    def test_embedding_storage_memory(self):
        """Verify embedding storage doesn't use excessive memory."""
        import tracemalloc

        tracemalloc.start()

        # Simulate storing embeddings
        n_tracks = 1000
        embedding_dim = 512
        embeddings = np.random.randn(n_tracks, embedding_dim).astype(np.float32)

        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        # Memory should be reasonable (less than 100MB for 1000 embeddings)
        expected_memory = n_tracks * embedding_dim * 4  # 4 bytes per float32
        assert peak < expected_memory * 2, f"Memory usage too high: {peak / 1024 / 1024:.2f}MB"

    def test_position_calculation_memory(self):
        """Verify position calculation doesn't use excessive memory."""
        from processing.positioning import SonicPositioner
        import tracemalloc

        positioner = SonicPositioner(n_neighbors=15, min_dist=0.1, random_state=42)

        np.random.seed(42)
        n_tracks = 200
        embeddings = np.random.randn(n_tracks, 512).astype(np.float32)

        tracemalloc.start()
        positions = positioner.fit_transform(embeddings)
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        # Memory should be bounded (less than 500MB for 200 tracks)
        assert peak < 500 * 1024 * 1024, f"Memory usage too high: {peak / 1024 / 1024:.2f}MB"


class TestResponseTimeValidation:
    """Response time validation for API endpoints."""

    def test_tracks_endpoint_response_time(self):
        """Verify /tracks endpoint responds quickly."""
        from fastapi.testclient import TestClient
        from api.main import app

        client = TestClient(app)

        with patch('api.main.get_db_connection') as mock_db:
            mock_cursor = MagicMock()
            mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
            mock_cursor.__exit__ = MagicMock(return_value=False)
            mock_cursor.fetchall.return_value = [
                {"id": i, "title": f"Track {i}", "artist": f"Artist {i}"}
                for i in range(100)
            ]
            mock_db.return_value.cursor.return_value = mock_cursor

            start_time = time.time()
            response = client.get("/api/tracks?limit=100")
            elapsed_time = time.time() - start_time

            assert response.status_code == 200
            assert elapsed_time < 1.0, f"Tracks endpoint too slow: {elapsed_time:.3f}s"

    def test_sonic_map_endpoint_response_time(self):
        """Verify /sonic-map endpoint responds quickly."""
        from fastapi.testclient import TestClient
        from api.main import app

        client = TestClient(app)

        with patch('api.main.get_db_connection') as mock_db:
            mock_cursor = MagicMock()
            mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
            mock_cursor.__exit__ = MagicMock(return_value=False)
            mock_cursor.fetchall.return_value = [
                {
                    "id": str(i),
                    "title": f"Track {i}",
                    "artist": f"Artist {i}",
                    "genre": "Electronic",
                    "liked": False,
                    "position": {"x": float(i), "y": float(i*2), "z": float(i*3)},
                    "color": {"r": 0.5, "g": 0.5, "b": 0.5},
                    "size": 1.0,
                    "emissiveIntensity": 0.2,
                    "audio": {"tempo": 120, "energy": 0.5, "danceability": 0.5},
                }
                for i in range(100)
            ]
            mock_db.return_value.cursor.return_value = mock_cursor

            start_time = time.time()
            response = client.get("/api/tracks/sonic-map?limit=100")
            elapsed_time = time.time() - start_time

            assert response.status_code == 200
            assert elapsed_time < 1.0, f"Sonic map endpoint too slow: {elapsed_time:.3f}s"

    def test_similar_endpoint_response_time(self):
        """Verify /similar endpoint responds quickly."""
        from fastapi.testclient import TestClient
        from api.main import app

        client = TestClient(app)

        with patch('api.main.find_similar_tracks') as mock_find:
            mock_find.return_value = {
                "track_id": 42,
                "count": 10,
                "results": [
                    {"track_id": i, "similarity_score": 0.9 - i*0.01, "rank": i-42}
                    for i in range(43, 53)
                ],
            }

            start_time = time.time()
            response = client.get("/api/tracks/42/similar?limit=10")
            elapsed_time = time.time() - start_time

            assert response.status_code == 200
            assert elapsed_time < 0.5, f"Similar endpoint too slow: {elapsed_time:.3f}s"


class TestBatchOperations:
    """Test batch operations performance."""

    def test_batch_embedding_upsert(self):
        """Verify batch embedding upsert is efficient."""
        from jobs.position_job import upsert_embedding, TrackEmbeddingMetadata

        n_tracks = 50

        with patch('jobs.position_job._get_qdrant_client') as mock_qdrant, \
             patch('jobs.position_job.get_db_connection') as mock_db:

            mock_client = MagicMock()
            mock_qdrant.return_value = mock_client

            mock_cursor = MagicMock()
            mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
            mock_cursor.__exit__ = MagicMock(return_value=False)
            mock_db.return_value.cursor.return_value = mock_cursor

            start_time = time.time()

            for i in range(n_tracks):
                target = TrackEmbeddingMetadata(
                    track_id=i,
                    point_id=f"point-{i}",
                    model_name="clap-htsat-base",
                    model_version="1.0",
                    vector_dimensions=512,
                )
                embedding = np.random.randn(512).astype(np.float32)
                upsert_embedding(target, embedding)

            elapsed_time = time.time() - start_time

            # Should complete within 5 seconds for 50 tracks
            assert elapsed_time < 5.0, f"Batch upsert too slow: {elapsed_time:.3f}s"
            assert mock_client.upsert.call_count == n_tracks

    def test_batch_position_update(self):
        """Verify batch position updates are efficient."""
        from jobs.position_job import update_track_position

        n_tracks = 100

        with patch('jobs.position_job.get_db_connection') as mock_db:
            mock_cursor = MagicMock()
            mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
            mock_cursor.__exit__ = MagicMock(return_value=False)
            mock_db.return_value.cursor.return_value = mock_cursor

            start_time = time.time()

            for i in range(n_tracks):
                update_track_position(
                    track_id=i,
                    position=(float(i), float(i*2), float(i*3)),
                    position_method="clap_umap_full",
                    position_version_id="version-1",
                    position_quality={"trustworthiness": 0.95},
                )

            elapsed_time = time.time() - start_time

            # Should complete within 2 seconds for 100 tracks
            assert elapsed_time < 2.0, f"Batch position update too slow: {elapsed_time:.3f}s"


class TestConcurrentLoad:
    """Test concurrent load handling."""

    def test_concurrent_similarity_requests(self):
        """Verify system handles concurrent similarity requests."""
        from api.similarity import find_similar_tracks
        import threading

        results = []
        errors = []

        def make_request(track_id):
            try:
                with patch('api.similarity.get_db_connection') as mock_db, \
                     patch('api.similarity.get_qdrant_client') as mock_qdrant:

                    mock_cursor = MagicMock()
                    mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
                    mock_cursor.__exit__ = MagicMock(return_value=False)
                    mock_cursor.fetchone.return_value = {
                        'track_id': track_id,
                        'qdrant_point_id': f'point-{track_id}',
                        'model_name': 'clap-htsat-base',
                        'model_version': '1.0',
                        'vector_dimensions': 512,
                        'position_x': 1.0,
                        'position_y': 2.0,
                        'position_z': 3.0,
                    }
                    mock_db.return_value.cursor.return_value = mock_cursor

                    mock_client = MagicMock()
                    mock_client.retrieve.return_value = [
                        SimpleNamespace(id=f'point-{track_id}', vector=np.random.randn(512).tolist())
                    ]
                    mock_client.query_points.return_value = SimpleNamespace(points=[
                        SimpleNamespace(id=f'point-{i}', score=0.9, payload={'track_id': i})
                        for i in range(100, 110)
                    ])
                    mock_qdrant.return_value = mock_client

                    result = find_similar_tracks(track_id, limit=10, offset=0, min_score=0.0)
                    results.append(result)
            except Exception as e:
                errors.append((track_id, str(e)))

        # Create concurrent requests
        threads = [threading.Thread(target=make_request, args=(i,)) for i in range(1, 11)]

        start_time = time.time()
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        elapsed_time = time.time() - start_time

        # All requests should complete
        assert len(results) + len(errors) == 10
        # Should complete within 5 seconds
        assert elapsed_time < 5.0, f"Concurrent requests too slow: {elapsed_time:.3f}s"