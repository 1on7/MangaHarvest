import base64

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
    assert response.json()["status"] == "ok"


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
    assert response.json() == {"results": [{"name": "Example Manga", "status": "not_found"}]}
