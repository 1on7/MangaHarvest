import re

import requests


BASE_URL = "https://api.mangaupdates.com/v1"
TIMEOUT = 15


def _request(method, url, **kwargs):
    response = requests.request(method, url, timeout=TIMEOUT, **kwargs)
    response.raise_for_status()
    return response.json()


def get_manga_updates_data(search_query):
    try:
        data = _request(
            "POST",
            f"{BASE_URL}/series/search",
            json={"search": search_query, "page": 1},
        )
        results = data.get("results") or []
        if not results:
            return None

        record = (results[0] or {}).get("record") or {}
        series_id = record.get("series_id")
        if not series_id:
            return None

        associated, status = get_manga_associated(series_id)
        return (
            record.get("type"),
            record.get("year"),
            record.get("bayesian_rating"),
            [item.get("genre") for item in record.get("genres", []) if item.get("genre")],
            associated or [],
            status or "",
        )
    except (requests.RequestException, ValueError, TypeError, KeyError):
        return None


def get_manga_associated(series_id):
    try:
        data = _request("GET", f"{BASE_URL}/series/{series_id}")
        associated = data.get("associated") or []
        status_text = data.get("status") or ""
        match = re.search(r"\d+ .*?\((.*?)\)", status_text)
        return associated, match.group(1) if match else ""
    except (requests.RequestException, ValueError, TypeError, KeyError):
        return [], ""
