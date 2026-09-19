import datetime
import json
import sys
from os import path
from urllib.parse import quote

from bs4 import BeautifulSoup

sys.path.append(path.dirname(path.dirname(path.abspath(__file__))))

from MangaSite.http import fetch_json, fetch_text, gather_limited
from MangaSite.parser_utils import absolute_url, best_match, chapter_number, extract_image_urls

BASE_URL = "https://dilar.tube"
_HEADERS = {"Accept": "application/json,text/html,*/*", "User-Agent": "MangaHarvest/2.2"}

async def dilar_info(name):
    try:
        response = await fetch_json(
            f"{BASE_URL}/api/quick_search",
            method="POST",
            json={"query": name, "includes": ["Manga", "Team", "Member"]},
            headers=_HEADERS,
        )
        if not response or not isinstance(response, list):
            return "not found"
        items = (response[0] or {}).get("data") or []
        manga = best_match(items, name)
        if not manga:
            return "not found"
        latest = chapter_number(manga.get("latest_chapter"))
        manga_id = manga.get("id")
        cover = manga.get("cover", "")
        return {
            "title": manga.get("title", name),
            "summary": manga.get("summary", ""),
            "cover": f"{BASE_URL}/uploads/manga/cover/{manga_id}/{cover}" if cover else "",
            "id": manga_id,
            "latest_chapter": latest,
        }
    except Exception:
        return "not found"

async def dilar_chapter_imgs(chapter_url):
    try:
        text = await fetch_text(chapter_url, headers={"Accept": "text/html,*/*"})
        soup = BeautifulSoup(text, "html.parser")
        script = soup.find("script", class_="js-react-on-rails-component")
        if script and script.string:
            data = json.loads(script.string)
            release = data.get("readerDataAction", {}).get("readerData", {}).get("release", {})
            storage_key = release.get("storage_key")
            pages = release.get("pages") or []
            if storage_key:
                return [
                    f"{BASE_URL}/uploads/releases/{storage_key}/hq/{page}"
                    for page in pages
                    if str(page).strip()
                ]
        return extract_image_urls(soup, base_url=chapter_url)
    except Exception:
        return []

def _release_date(timestamp):
    try:
        return datetime.datetime.fromtimestamp(float(timestamp), tz=datetime.timezone.utc).strftime("%Y-%m-%d") if timestamp else ""
    except (TypeError, ValueError, OSError):
        return ""

async def dilar_chapters(id, title, *, min_chapter=None):
    if not id:
        return None
    try:
        response = await fetch_json(f"{BASE_URL}/api/mangas/{id}/releases", headers=_HEADERS)
        chapters = {}
        for release in (response or {}).get("releases", []):
            number = chapter_number(release.get("chapter"))
            if number is None:
                continue

            raw_url = release.get("url") or release.get("chapter_url")
            chapter_url = absolute_url(BASE_URL, raw_url) if raw_url else (
                f"{BASE_URL}/mangas/{id}/{quote(str(title or '').replace(' ', '-'), safe='-')}/{number}"
            )
            if not chapter_url:
                continue

            chapters[number] = {
                "chapter": number,
                "chapter_url": chapter_url,
                "teams": [{
                    "team_name": "Dilar",
                    "chapter_date": _release_date(release.get("time_stamp")),
                    "chapter_page": [],
                }],
            }

        selected = [item for item in chapters.values() if min_chapter is None or item["chapter"] > min_chapter]
        pages = await gather_limited([dilar_chapter_imgs(item["chapter_url"]) for item in selected], limit=6, return_exceptions=True)
        for item, value in zip(selected, pages):
            item["teams"][0]["chapter_page"] = value if isinstance(value, list) else []

        for item in chapters.values():
            item.pop("chapter_url", None)
        return list(chapters.values())
    except Exception:
        return None
