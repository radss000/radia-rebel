from fastapi.testclient import TestClient

from api import main as api_main
from api.similarity import SimilarityServiceError


client = TestClient(api_main.app)


def test_similar_endpoint_forwards_validated_parameters(monkeypatch):
    captured = {}

    def fake_find(track_id, limit, offset, min_score):
        captured.update(
            track_id=track_id,
            limit=limit,
            offset=offset,
            min_score=min_score,
        )
        return {"track_id": track_id, "count": 0, "results": []}

    monkeypatch.setattr(api_main, "find_similar_tracks", fake_find)

    response = client.get("/api/tracks/42/similar?limit=7&offset=2&min_score=0.4")

    assert response.status_code == 200
    assert response.json()["track_id"] == 42
    assert captured == {"track_id": 42, "limit": 7, "offset": 2, "min_score": 0.4}


def test_similar_endpoint_maps_service_errors(monkeypatch):
    def fake_find(track_id, limit, offset, min_score):
        raise SimilarityServiceError(409, "Track does not have a searchable embedding")

    monkeypatch.setattr(api_main, "find_similar_tracks", fake_find)

    response = client.get("/api/tracks/42/similar")

    assert response.status_code == 409
    assert response.json()["detail"] == "Track does not have a searchable embedding"


def test_similar_endpoint_rejects_unbounded_parameters():
    response = client.get("/api/tracks/42/similar?limit=500&offset=-1&min_score=2")

    assert response.status_code == 422
