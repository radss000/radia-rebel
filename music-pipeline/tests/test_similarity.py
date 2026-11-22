from types import SimpleNamespace

import api.similarity as similarity
from api.similarity import (
    EmbeddingMetadata,
    build_similarity_results,
    classify_similarity,
    load_similarity_calibration,
)


def _point(track_id, score):
    return SimpleNamespace(payload={"track_id": track_id}, score=score)


def _row(track_id, model="clap-htsat-base", version="1.0", dimensions=512):
    return {
        "id": track_id,
        "title": f"Track {track_id}",
        "artist": "REBEL",
        "album": None,
        "genre": "electronic",
        "year": 2026,
        "preview_url": None,
        "position_x": float(track_id),
        "position_y": 0.0,
        "position_z": 0.0,
        "position_method": "clap_umap_full",
        "model_name": model,
        "model_version": version,
        "vector_dimensions": dimensions,
    }


TARGET = EmbeddingMetadata(
    track_id=1,
    qdrant_point_id="target-point",
    model_name="clap-htsat-base",
    model_version="1.0",
    vector_dimensions=512,
    position_x=0.0,
    position_y=0.0,
    position_z=0.0,
)


def test_similarity_results_exclude_self_duplicates_and_incompatible_embeddings():
    points = [
        _point(1, 1.0),
        _point(2, 0.91),
        _point(2, 0.90),
        _point(3, 0.89),
        _point(4, 0.88),
    ]
    rows = {
        2: _row(2),
        3: _row(3, version="2.0"),
        4: _row(4, dimensions=1024),
    }

    results = build_similarity_results(points, rows, TARGET, limit=10, offset=0, min_score=0.0)

    assert [result["track_id"] for result in results] == [2]
    assert results[0]["similarity_score"] == 0.91
    assert results[0]["rank"] == 1
    assert results[0]["distance_3d"] == 2.0


def test_similarity_results_are_deterministic_paginated_and_thresholded():
    points = [_point(4, 0.70), _point(3, 0.90), _point(2, 0.90), _point(5, 0.40)]
    rows = {track_id: _row(track_id) for track_id in (2, 3, 4, 5)}

    results = build_similarity_results(points, rows, TARGET, limit=2, offset=1, min_score=0.5)

    assert [result["track_id"] for result in results] == [3, 4]
    assert [result["rank"] for result in results] == [2, 3]


def test_similarity_bands_require_valid_calibration():
    thresholds = {"very_close": 0.9, "close": 0.8, "related": 0.65}

    assert classify_similarity(0.95, thresholds) == "very_close"
    assert classify_similarity(0.85, thresholds) == "close"
    assert classify_similarity(0.70, thresholds) == "related"
    assert classify_similarity(0.50, thresholds) == "weak"
    assert classify_similarity(0.95, None) is None


def test_versioned_calibration_must_be_explicitly_active(monkeypatch, tmp_path):
    calibration_path = tmp_path / "calibration.json"
    calibration_path.write_text(
        '{"schema_version":1,"active":false,"thresholds":'
        '{"very_close":0.9,"close":0.8,"related":0.65}}'
    )
    monkeypatch.setenv("SIMILARITY_CALIBRATION_PATH", str(calibration_path))
    for env_name in (
        "SIMILARITY_VERY_CLOSE_THRESHOLD",
        "SIMILARITY_CLOSE_THRESHOLD",
        "SIMILARITY_RELATED_THRESHOLD",
    ):
        monkeypatch.delenv(env_name, raising=False)

    assert load_similarity_calibration() is None

    calibration_path.write_text(
        '{"schema_version":1,"active":true,"calibration_id":"cal-v1",'
        '"corpus_id":"rebel-validation","corpus_version":"1.0",'
        '"thresholds":{"very_close":0.9,"close":0.8,"related":0.65}}'
    )
    calibration = load_similarity_calibration()

    assert calibration["calibration_id"] == "cal-v1"
    assert calibration["thresholds"]["close"] == 0.8


def test_find_similar_tracks_queries_qdrant_and_closes_connection(monkeypatch):
    class FakeConnection:
        closed = False

        def close(self):
            self.closed = True

    class FakeQdrant:
        query_kwargs = None

        def retrieve(self, **kwargs):
            return [SimpleNamespace(vector=[1.0, 0.0])]

        def query_points(self, **kwargs):
            self.query_kwargs = kwargs
            return SimpleNamespace(points=[_point(1, 1.0), _point(2, 0.9)])

    connection = FakeConnection()
    qdrant = FakeQdrant()
    monkeypatch.setattr(similarity, "get_db_connection", lambda: connection)
    monkeypatch.setattr(similarity, "get_qdrant_client", lambda: qdrant)
    monkeypatch.setattr(similarity, "_load_target_embedding", lambda conn, track_id: TARGET)
    monkeypatch.setattr(similarity, "_load_candidate_tracks", lambda conn, track_ids: {2: _row(2)})

    response = similarity.find_similar_tracks(1, limit=10, offset=0, min_score=0.5)

    assert response["metric"] == "cosine"
    assert response["results"][0]["track_id"] == 2
    assert qdrant.query_kwargs["score_threshold"] == 0.5
    assert qdrant.query_kwargs["with_vectors"] is False
    assert connection.closed is True
