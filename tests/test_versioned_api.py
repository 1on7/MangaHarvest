import os

os.environ.setdefault("MONGO_URI", "mongodb://localhost:27017/test")

from fastapi.testclient import TestClient

from api.app import app


def test_versioned_info_route(monkeypatch):
    import api.app as api_app

    async def fake_info(manga_id):
        return {"id": manga_id, "title": "Example"}

    monkeypatch.setattr(api_app, "info_manga", fake_info)
    response = TestClient(app).get("/api/v1/manga/123")
    assert response.status_code == 200
    assert response.json() == {"id": "123", "title": "Example"}


def test_versioned_chapters_route(monkeypatch):
    import api.app as api_app

    async def fake_chapters(manga_id):
        return {"id": manga_id, "chapters": []}

    monkeypatch.setattr(api_app, "chapters_manga", fake_chapters)
    response = TestClient(app).get("/api/v1/manga/123/chapters")
    assert response.status_code == 200
    assert response.json() == {"id": "123", "chapters": []}


def test_versioned_search_route(monkeypatch):
    import api.app as api_app

    async def fake_search(name, page, limit):
        return {"page": page, "limit": limit, "count": 1, "results": [{"title": name}]}

    monkeypatch.setattr(api_app, "search_manga", fake_search)
    response = TestClient(app).get(
        "/api/v1/manga/search",
        params={"name": "Solo Leveling", "page": 2, "limit": 10},
    )
    assert response.status_code == 200
    assert response.json()["page"] == 2
    assert response.json()["results"][0]["title"] == "Solo Leveling"


def test_versioned_latest_route(monkeypatch):
    import api.app as api_app

    async def fake_latest(page, limit):
        return {"page": page, "limit": limit, "count": 1, "results": [{"title": "Latest"}]}

    monkeypatch.setattr(api_app, "latest_manga", fake_latest)
    response = TestClient(app).get(
        "/api/v1/manga/latest",
        params={"page": 1, "limit": 10},
    )
    assert response.status_code == 200
    assert response.json()["results"][0]["title"] == "Latest"
