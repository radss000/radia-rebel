from types import SimpleNamespace

import numpy as np

import jobs.position_job as position_job
from processing.positioning import NeighborPositionResult


TARGET = position_job.TrackEmbeddingMetadata(
    track_id=10,
    point_id="point-10",
    model_name="clap-htsat-base",
    model_version="1.0",
    vector_dimensions=4,
)


class StaticPositioner:
    def __init__(self, metrics):
        self.metrics = metrics

    def fit_transform(self, embeddings):
        return np.arange(len(embeddings) * 3, dtype=np.float32).reshape(len(embeddings), 3)

    def quality_metrics(self, embeddings, positions, n_neighbors):
        return dict(self.metrics)

    def align_to_anchors(self, positions, anchor_indices, anchor_positions):
        return positions


def test_full_map_is_rejected_before_publication_when_quality_is_low(monkeypatch):
    rejected = []
    monkeypatch.setattr(position_job, "get_anchor_positions", lambda track_ids: {})
    monkeypatch.setattr(
        position_job,
        "record_rejected_map",
        lambda target, count, metrics, fingerprint, reason: rejected.append(reason),
    )
    monkeypatch.setattr(
        position_job,
        "publish_full_map",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not publish")),
    )
    positioner = StaticPositioner(
        {"trustworthiness": 0.95, "neighbor_recall": 0.2, "quality_k": 2}
    )
    embeddings = np.eye(5, 4, dtype=np.float32)

    with np.testing.assert_raises(position_job.PositionQualityError):
        position_job.recalculate_full_map(positioner, TARGET, embeddings, [10, 11, 12, 13, 14])

    assert rejected and "neighbor_recall" in rejected[0]


def test_full_map_returns_versioned_position_after_quality_gate(monkeypatch):
    monkeypatch.setattr(position_job, "get_anchor_positions", lambda track_ids: {})
    monkeypatch.setattr(position_job, "publish_full_map", lambda *args, **kwargs: "map-version")
    positioner = StaticPositioner(
        {"trustworthiness": 0.96, "neighbor_recall": 0.8, "quality_k": 2}
    )
    embeddings = np.eye(5, 4, dtype=np.float32)

    result = position_job.recalculate_full_map(
        positioner,
        TARGET,
        embeddings,
        [10, 11, 12, 13, 14],
    )

    assert result["position_method"] == "clap_umap_full"
    assert result["position_version_id"] == "map-version"
    assert result["x"] == 0.0


def test_approximate_position_excludes_target_and_records_neighbors(monkeypatch):
    captured = {}
    candidate_embeddings = np.array([[1.0, 0.0], [0.8, 0.2], [0.7, 0.3]], dtype=np.float32)
    candidate_positions = np.array(
        [[10.0, 0.0, 0.0], [20.0, 0.0, 0.0], [30.0, 0.0, 0.0]],
        dtype=np.float32,
    )

    def fake_subset(embeddings, track_ids, exclude_track_id):
        captured["exclude_track_id"] = exclude_track_id
        return candidate_embeddings, candidate_positions, [11, 12, 13]

    class FakePositioner:
        def nearest_neighbor_position_with_details(self, *args, **kwargs):
            return NeighborPositionResult(
                position=np.array([14.0, 0.0, 0.0], dtype=np.float32),
                neighbor_indices=np.array([0, 1]),
                similarities=np.array([0.9, 0.8], dtype=np.float32),
            )

    monkeypatch.setattr(position_job, "get_positioned_embedding_subset", fake_subset)
    monkeypatch.setattr(position_job, "get_current_published_version", lambda: "map-version")
    monkeypatch.setattr(
        position_job,
        "update_track_position",
        lambda track_id, x, y, z, method, version_id, quality: captured.update(
            track_id=track_id,
            method=method,
            version_id=version_id,
            quality=quality,
        ),
    )

    result = position_job.approximate_track_position(
        FakePositioner(),
        TARGET,
        np.array([1.0, 0.0], dtype=np.float32),
        np.zeros((4, 2), dtype=np.float32),
        [10, 11, 12, 13],
    )

    assert captured["exclude_track_id"] == 10
    assert captured["track_id"] == 10
    assert captured["method"] == "clap_knn_approx"
    assert captured["quality"]["neighbor_track_ids"] == [11, 12]
    assert result["position_version_id"] == "map-version"


def test_compatible_embeddings_keep_current_qdrant_point_and_sort(monkeypatch):
    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def execute(self, query, params):
            return None

        def fetchall(self):
            return [(10, "current-10"), (11, "current-11")]

    class FakeConnection:
        def cursor(self):
            return FakeCursor()

        def close(self):
            return None

    points = [
        SimpleNamespace(id="old-10", payload={"track_id": 10}, vector=[9, 9, 9, 9]),
        SimpleNamespace(id="current-11", payload={"track_id": 11}, vector=[1, 1, 1, 1]),
        SimpleNamespace(id="current-10", payload={"track_id": 10}, vector=[2, 2, 2, 2]),
    ]
    client = SimpleNamespace(scroll=lambda **kwargs: (points, None))
    monkeypatch.setattr(position_job, "_get_qdrant_client", lambda: client)
    monkeypatch.setattr(position_job, "get_db_connection", lambda: FakeConnection())

    embeddings, track_ids = position_job.get_compatible_embeddings(TARGET)

    assert track_ids == [10, 11]
    assert embeddings.tolist() == [[2.0, 2.0, 2.0, 2.0], [1.0, 1.0, 1.0, 1.0]]


def test_full_map_publication_commits_staging_and_track_update_atomically(monkeypatch):
    statements = []
    staged_rows = []

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def execute(self, query, params=None):
            statements.append(" ".join(query.split()))

    class FakeConnection:
        committed = False
        rolled_back = False

        def cursor(self):
            return FakeCursor()

        def commit(self):
            self.committed = True

        def rollback(self):
            self.rolled_back = True

        def close(self):
            return None

    connection = FakeConnection()
    monkeypatch.setattr(position_job, "get_db_connection", lambda: connection)
    monkeypatch.setattr(position_job.uuid, "uuid4", lambda: "map-version")
    monkeypatch.setattr(
        position_job,
        "execute_values",
        lambda cursor, query, rows: staged_rows.extend(rows),
    )

    version_id = position_job.publish_full_map(
        TARGET,
        [10, 11],
        np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]], dtype=np.float32),
        {"trustworthiness": 0.95, "neighbor_recall": 0.8},
        "fingerprint",
    )

    assert version_id == "map-version"
    assert len(staged_rows) == 2
    assert any("UPDATE tracks t" in statement for statement in statements)
    assert any("status = 'published'" in statement for statement in statements)
    assert connection.committed is True
    assert connection.rolled_back is False


def test_full_map_publication_rolls_back_as_one_transaction(monkeypatch):
    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def execute(self, query, params=None):
            if "UPDATE tracks t" in query:
                raise RuntimeError("publication failed")

    class FakeConnection:
        committed = False
        rolled_back = False

        def cursor(self):
            return FakeCursor()

        def commit(self):
            self.committed = True

        def rollback(self):
            self.rolled_back = True

        def close(self):
            return None

    connection = FakeConnection()
    monkeypatch.setattr(position_job, "get_db_connection", lambda: connection)
    monkeypatch.setattr(position_job, "execute_values", lambda cursor, query, rows: None)

    with np.testing.assert_raises_regex(RuntimeError, "publication failed"):
        position_job.publish_full_map(
            TARGET,
            [10],
            np.array([[1.0, 2.0, 3.0]], dtype=np.float32),
            {"trustworthiness": 0.95, "neighbor_recall": 0.8},
            "fingerprint",
        )

    assert connection.committed is False
    assert connection.rolled_back is True
