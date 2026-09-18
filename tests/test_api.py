import base64
import os
import sys
from pathlib import Path

os.environ.setdefault("MONGO_URI", "mongodb://localhost:27017/test")

from fastapi.testclient import TestClient

from api.app import app, clean_name, chapter_number


def test_clean_name():
    assert clean_name("  Solo   Leveling  ") == "Solo Leveling"


def test_chapter_number():
    assert chapter_number("12.5") == 12.5
    assert chapter_number(None) == -1


def test_health():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "MangaHarvest"}


def test_add_rejects_invalid_base64():
    client = TestClient(app)
    response = client.post("/manga/add", json={"data": "%%%not-base64%%%"})
    assert response.status_code == 400


def test_add_accepts_base64_shape(monkeypatch):
    import api.app as api_app

    async def fake_source(name):
        return None

    monkeypatch.setattr(api_app, "find_best_source", fake_source)
    client = TestClient(app)
    encoded = base64.b64encode(b"Example Manga\n\n").decode()
    response = client.post("/manga/add", json={"data": encoded})
    assert response.status_code == 200
    assert response.json() == {
        "results": [{"name": "Example Manga", "status": "not_found"}]
    }


def test_search_uses_threaded_database_helper(monkeypatch):
    import api.app as api_app

    class FakeCollection:
        pass

    expected = [{"_id": "507f1f77bcf86cd799439011", "title": "Solo Leveling"}]

    monkeypatch.setattr(
        api_app,
        "_search_manga_documents",
        lambda name, skip, limit: expected,
    )

    response = TestClient(api_app.app).get(
        "/manga/search", params={"name": "solo", "page": 1, "limit": 20}
    )
    assert response.status_code == 200
    assert response.json()["results"][0]["title"] == "Solo Leveling"


def test_search_validation():
    client = TestClient(app)
    response = client.get("/manga/search", params={"name": ""})
    assert response.status_code == 422
