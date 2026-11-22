from fastapi.testclient import TestClient

from api import main as api_main


client = TestClient(api_main.app)


class FakeCursor:
    def __init__(self, row):
        self.row = row

    def execute(self, query, params=None):
        return None

    def fetchone(self):
        return self.row

    def close(self):
        return None


class FakeConnection:
    def __init__(self, row):
        self.row = row

    def cursor(self, cursor_factory=None):
        return FakeCursor(self.row)

    def close(self):
        return None


def test_sonic_map_version_endpoint_returns_published_provenance(monkeypatch):
    version = {
        "id": "map-version",
        "status": "published",
        "method": "clap_umap_full",
        "model_name": "clap-htsat-base",
        "model_version": "1.0",
        "vector_dimensions": 512,
        "track_count": 100,
        "umap_params": {"n_neighbors": 15},
        "metrics": {"trustworthiness": 0.95, "neighbor_recall": 0.8},
        "catalog_fingerprint": "fingerprint",
        "created_at": None,
        "published_at": None,
    }
    monkeypatch.setattr(api_main, "get_db_connection", lambda: FakeConnection(version))

    response = client.get("/api/sonic-map/version")

    assert response.status_code == 200
    assert response.json()["id"] == "map-version"
    assert response.json()["metrics"]["trustworthiness"] == 0.95


def test_sonic_map_version_endpoint_returns_404_without_publication(monkeypatch):
    monkeypatch.setattr(api_main, "get_db_connection", lambda: FakeConnection(None))

    response = client.get("/api/sonic-map/version")

    assert response.status_code == 404
