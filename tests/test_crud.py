import mongomock
import os

os.environ.setdefault("MONGO_URI", "mongodb://localhost:27017/test")

from fastapi.testclient import TestClient

from api.app import app
import api.app as api_app


def _use_mock_db(monkeypatch):
    client = mongomock.MongoClient()
    database = client["manga_db"]
    monkeypatch.setattr(api_app.db, "collection_mamga_info", database["info"])
    monkeypatch.setattr(api_app.db, "collection_mamga_chapters", database["chapters"])


def test_crud_info_chapters_update_delete(monkeypatch):
    _use_mock_db(monkeypatch)
    info = api_app.db.collection_mamga_info
    chapters = api_app.db.collection_mamga_chapters

    manga_id = info.insert_one({
        "title": "Solo Leveling",
        "summary": "Original summary",
        "cover": "cover.jpg",
    }).inserted_id
    manga_id = str(manga_id)
    chapters.insert_one({
        "manga_id": manga_id,
        "chapters": [{"chapter": 1, "teams": []}],
    })

    client = TestClient(app)

    response = client.get("/manga/", params={"manga_id": manga_id})
    assert response.status_code == 200
    assert response.json()["title"] == "Solo Leveling"

    response = client.get(f"/manga/chapters/{manga_id}")
    assert response.status_code == 200
    assert response.json()["chapters"][0]["chapter"] == 1

    response = client.put(f"/manga/{manga_id}", json={"summary": "Updated"})
    assert response.status_code == 200
    stored = info.find_one({"title": "Solo Leveling"})
    assert stored["summary"] == "Updated"

    response = client.delete(f"/manga/{manga_id}")
    assert response.status_code == 200
    assert info.find_one({"title": "Solo Leveling"}) is None
    assert chapters.find_one({"manga_id": manga_id}) is None


def test_crud_invalid_and_missing_ids(monkeypatch):
    _use_mock_db(monkeypatch)
    client = TestClient(app)

    response = client.get("/manga/", params={"manga_id": "invalid"})
    assert response.status_code == 400

    response = client.put("/manga/507f1f77bcf86cd799439011", json={"summary": "x"})
    assert response.status_code == 404

    response = client.delete("/manga/507f1f77bcf86cd799439011")
    assert response.status_code == 404
