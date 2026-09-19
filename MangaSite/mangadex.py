from __future__ import annotations

from urllib.parse import urlencode

from MangaSite.http import fetch_json, gather_limited
from MangaSite.parser_utils import best_match, chapter_number

API = "https://api.mangadex.org"
_HEADERS = {"Accept": "application/json"}


def _localized_title(attributes: dict) -> str:
    titles = attributes.get("title") or {}
    for language in ("en", "ko", "ja", "zh"):
        if titles.get(language):
            return str(titles[language])
    return next(iter(titles.values()), "") if titles else ""


def _cover_url(manga_id: str, relationships: list[dict]) -> str:
    for rel in relationships or []:
        if rel.get("type") == "cover_art":
            attrs = rel.get("attributes") or {}
            filename = attrs.get("fileName")
            if filename:
                return f"https://uploads.mangadex.org/covers/{manga_id}/{filename}.512.jpg"
    return ""


async def mangadex_search(name: str):
    params = urlencode({
        "title": name,
        "limit": 10,
        "contentRating[]": ["safe", "suggestive"],
        "order[relevance]": "desc",
        "includes[]": ["cover_art"],
    }, doseq=True)
    data = await fetch_json(f"{API}/manga?{params}", headers=_HEADERS)
    items = []
    for item in data.get("data") or []:
        attrs = item.get("attributes") or {}
        title = _localized_title(attrs)
        aliases = [
            next(iter(value.values()))
            for value in (attrs.get("altTitles") or [])
            if isinstance(value, dict) and value
        ]
        items.append({
            "title": title,
            "alternative_titles": aliases,
            "id": item.get("id"),
            "cover": _cover_url(item.get("id", ""), item.get("relationships") or []),
            "_attributes": attrs,
        })

    match = best_match(items, name, title_keys=("title", "name", "post_title"))
    if not match or not match.get("id"):
        return "not found"

    attrs = match.get("_attributes") or {}
    description = attrs.get("description") or {}
    summary = description.get("en") or next(iter(description.values()), "") if description else ""
    tags = []
    for tag in attrs.get("tags") or []:
        tag_name = (tag.get("attributes") or {}).get("name") or {}
        value = tag_name.get("en") or next(iter(tag_name.values()), "") if tag_name else ""
        if value:
            tags.append(value)

    return {
        "title": match["title"],
        "alternative_titles": match.get("alternative_titles") or [],
        "summary": summary,
        "cover": match.get("cover", ""),
        "id": match["id"],
        "latest_chapter": None,
        "year": attrs.get("year"),
        "status": attrs.get("status") or "",
        "type": attrs.get("publicationDemographic") or "",
        "genres": tags,
        "source": "mangadex",
        "mangadex_id": match["id"],
    }


async def _chapter_pages(chapter_id: str) -> list[str]:
    data = await fetch_json(f"{API}/at-home/server/{chapter_id}", headers=_HEADERS)
    base = data.get("baseUrl")
    chapter = data.get("chapter") or {}
    digest = chapter.get("hash")
    files = chapter.get("dataSaver") or chapter.get("data") or []
    if not base or not digest:
        return []
    quality = "data-saver" if chapter.get("dataSaver") else "data"
    return [f"{base}/{quality}/{digest}/{filename}" for filename in files]


async def mangadex_chapters(manga_id: str, *, min_chapter=None):
    if not manga_id:
        return []
    params = {
        "manga[]": manga_id,
        "translatedLanguage[]": "en",
        "limit": 100,
        "offset": 0,
        "order[chapter]": "asc",
        "includeUnavailable": 0,
        "hasAvailableAtHome": "true",
    }
    chapters = []
    while True:
        query = urlencode(params, doseq=True)
        data = await fetch_json(f"{API}/chapter?{query}", headers=_HEADERS)
        batch = data.get("data") or []
        if not batch:
            break
        chapters.extend(batch)
        total = int(data.get("total") or 0)
        if len(chapters) >= total or len(batch) < 100:
            break
        params["offset"] += 100

    selected = []
    for item in chapters:
        attrs = item.get("attributes") or {}
        number = chapter_number(attrs.get("chapter"))
        if number is None:
            continue
        if min_chapter is not None and number <= min_chapter:
            continue
        selected.append((item, number))

    async def build(item_number):
        item, number = item_number
        attrs = item.get("attributes") or {}
        pages = await _chapter_pages(item.get("id"))
        if not pages:
            return None
        group = "mangadex"
        return {
            "chapter": number,
            "teams": [{
                "team_name": group,
                "chapter_date": attrs.get("publishAt") or "",
                "chapter_page": pages,
            }],
        }

    results = await gather_limited(
        [build(item) for item in selected],
        limit=4,
        return_exceptions=True,
    )
    return [item for item in results if isinstance(item, dict) and item.get("teams")]
