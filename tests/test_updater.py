import asyncio
import os

import mongomock

os.environ.setdefault("MONGO_URI", "mongodb://localhost:27017/test")

import api.app as api_app


def _use_mock_db(monkeypatch):
    client = mongomock.MongoClient()
    database = client["manga_db"]
    monkeypatch.setattr(api_app.db, "collection_mamga_info", database["info"])
    monkeypatch.setattr(api_app.db, "collection_mamga_chapters", database["chapters"])


def test_update_manga_library_skips_up_to_date(monkeypatch):
    _use_mock_db(monkeypatch)
    info = api_app.db.collection_mamga_info
    manga_id = info.insert_one({
        "title": "Solo Leveling",
        "latest_chapter": 10,
    }).inserted_id

    async def fake_source(title):
        return (1.0, 10, "gmanga", {"title": title})

    monkeypatch.setattr(api_app, "find_best_source", fake_source)

    async def fail_fetch(*args):
        raise AssertionError("chapter scraper should not run")

    monkeypatch.setattr(api_app, "fetch_chapters", fail_fetch)

    result = asyncio.run(api_app.update_manga_library())
    assert result[0]["status"] == "up_to_date"
    assert result[0]["latest_chapter"] == 10
    assert result[0]["id"] == str(manga_id)


def test_update_manga_library_updates_new_chapters(monkeypatch):
    _use_mock_db(monkeypatch)
    info = api_app.db.collection_mamga_info
    chapters = api_app.db.collection_mamga_chapters
    manga_id = info.insert_one({
        "title": "Solo Leveling",
        "latest_chapter": 10,
    }).inserted_id
    manga_id = str(manga_id)

    async def fake_source(title):
        return (1.0, 12, "gmanga", {"title": title, "post_url": "https://example.test"})

    async def fake_fetch(source, source_info):
        return [
            {"chapter": 11, "teams": [{"team_name": "Team", "chapter_date": "", "chapter_page": ["11.jpg"]}]},
            {"chapter": 12, "teams": [{"team_name": "Team", "chapter_date": "", "chapter_page": ["12.jpg"]}]},
        ]

    monkeypatch.setattr(api_app, "find_best_source", fake_source)
    monkeypatch.setattr(api_app, "fetch_chapters", fake_fetch)

    result = asyncio.run(api_app.update_manga_library())
    assert result[0]["status"] == "updated"
    assert result[0]["latest_chapter"] == 12
    assert result[0]["chapters"] == 2

    stored = info.find_one({"_id": manga_id})
    assert stored["latest_chapter"] == 12
    stored_chapters = chapters.find_one({"manga_id": manga_id})
    assert len(stored_chapters["chapters"]) == 2


def test_admin_update_requires_bearer_token(monkeypatch):
    from fastapi.testclient import TestClient

    _use_mock_db(monkeypatch)
    monkeypatch.setenv("ADMIN_UPDATE_TOKEN", "secret")

    response = TestClient(api_app.app).post("/api/v1/admin/update")
    assert response.status_code == 401

    async def fake_update(limit):
        return []

    monkeypatch.setattr(api_app, "update_manga_library", fake_update)
    response = TestClient(api_app.app).post(
        "/api/v1/admin/update",
        headers={"Authorization": "Bearer secret"},
    )
    assert response.status_code == 200
    assert response.json()["processed"] == 0
