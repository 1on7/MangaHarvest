import datetime
import json
import re
import sys
from os import path

from bs4 import BeautifulSoup

sys.path.append(path.dirname(path.dirname(path.abspath(__file__))))

from MangaSite.http import fetch_json, fetch_text


_HEADERS = {"Accept": "application/json,text/html,*/*", "User-Agent": "MangaHarvest/2.0"}


async def dilar_info(name):
    try:
        response = await fetch_json(
            "https://dilar.tube/api/quick_search",
            method="POST",
            json={"query": name, "includes": ["Manga", "Team", "Member"]},
            headers=_HEADERS,
        )
        if not response or not isinstance(response, list):
            return "not found"
        items = (response[0] or {}).get("data") or []
        if not items:
            return "not found"
        manga = items[0]
        latest = float(manga.get("latest_chapter", 0))
        if latest.is_integer():
            latest = int(latest)
        manga_id = manga.get("id")
        cover = manga.get("cover", "")
        return {
            "title": manga.get("title", name),
            "summary": manga.get("summary", ""),
            "cover": f"https://dilar.tube/uploads/manga/cover/{manga_id}/{cover}" if cover else "",
            "id": manga_id,
            "latest_chapter": latest,
        }
    except (ValueError, TypeError, KeyError, RuntimeError):
        return "not found"


async def dilar_chapter_imgs(chapter_url):
    try:
        text = await fetch_text(chapter_url, headers={"Accept": "text/html,*/*"})
        soup = BeautifulSoup(text, "html.parser")
        script = soup.find("script", class_="js-react-on-rails-component")
        if not script or not script.string:
            return []
        data = json.loads(script.string)
        release = data["readerDataAction"]["readerData"]["release"]
        storage_key = release["storage_key"]
        pages = release.get("pages") or []
        return [f"https://dilar.tube/uploads/releases/{storage_key}/hq/{page}" for page in pages]
    except (ValueError, TypeError, KeyError, RuntimeError):
        return []


async def dilar_chapters(id, title, *, min_chapter=None)
    try:
        response = await fetch_json(
            f"https://dilar.tube/api/mangas/{id}/releases",
            headers=_HEADERS,
        )
        chapters = {}
        for release in (response or {}).get("releases", []):
            chapter_num = release.get("chapter")
            if chapter_num is None:
                continue
            try:
                chapter_num = float(chapter_num)
                if chapter_num.is_integer():
                    chapter_num = int(chapter_num)
            except (ValueError, TypeError):
                continue
            chapter_url = f"https://dilar.tube/mangas/{id}/{str(title).replace(' ', '-')}/{chapter_num}"
            timestamp = release.get("time_stamp")
            chapter_date = datetime.datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d") if timestamp else ""
            chapters[(chapter_num, "Dilar")] = {
                "chapter": chapter_num,
                "teams": [{"team_name": "Dilar", "chapter_date": chapter_date, "chapter_page": (await dilar_chapter_imgs(chapter_url) if min_chapter is None or chapter_num > min_chapter else [])}],
            }
        return list(chapters.values())
    except (ValueError, TypeError, KeyError, RuntimeError):
        return None
