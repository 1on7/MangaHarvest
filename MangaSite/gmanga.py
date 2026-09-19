import re
import sys
from os import path
from urllib.parse import urlencode

from bs4 import BeautifulSoup

sys.path.append(path.dirname(path.dirname(path.abspath(__file__))))

from MangaSite.http import fetch_json, fetch_text, gather_limited
from MangaSite.parser_utils import absolute_url, best_match, chapter_number, extract_image_urls
from utils import date

_HEADERS = {
    "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
    "X-Requested-With": "XMLHttpRequest",
}

def _search_url(name):
    return "https://gmanga.site/?" + urlencode({"s": name, "post_type": "wp-manga"})

async def _gmanga_html_search(name):
    try:
        text = await fetch_text(_search_url(name), headers=_HEADERS)
        soup = BeautifulSoup(text, "html.parser")
        items = []
        for link in soup.select(".c-tabs-item__content .post-title a, .c-tabs-item__content .tab-thumb a, .row.c-tabs-item__content .post-title a"):
            href = link.get("href")
            title = link.get_text(" ", strip=True)
            if href:
                items.append({"title": title, "url": href})
        item = best_match(items, name)
        return item.get("url") if item else None
    except Exception:
        return None

async def gmanga_search(name):
    try:
        data = await fetch_json(
            "https://gmanga.site/wp-admin/admin-ajax.php",
            method="POST",
            data={"title": name, "action": "wp-manga-search-manga"},
            headers=_HEADERS,
        )
        item = best_match(data.get("data") or [], name)
        if item and item.get("url"):
            result = await gmanga_info(item["url"])
            if result != "not found":
                return result
    except Exception:
        pass

    fallback_url = await _gmanga_html_search(name)
    return await gmanga_info(fallback_url) if fallback_url else "not found"

async def gmanga_latest_chapters(post_url):
    try:
        text = await fetch_text(f"{post_url.rstrip('/')}/ajax/chapters/", method="POST", headers=_HEADERS)
        soup = BeautifulSoup(text, "html.parser")
        link = soup.select_one("li.wp-manga-chapter a")
        return chapter_number(link.get_text(" ", strip=True), href=link.get("href")) if link else None
    except Exception:
        return None

async def gmanga_info(url):
    if not url:
        return "not found"
    try:
        response_text = await fetch_text(url, headers=_HEADERS)
        soup = BeautifulSoup(response_text, "html.parser")
        title_node = soup.select_one(".post-title h1")
        summary_node = soup.select_one(".summary__content")
        if not title_node:
            return "not found"
        image_node = soup.select_one(".summary_image img")
        manga_id = re.search(r'"manga_id"\s*:\s*"?(\d+)', response_text)
        latest = await gmanga_latest_chapters(url)
        cover = ""
        if image_node:
            cover = image_node.get("data-src") or image_node.get("data-lazy-src") or image_node.get("src", "")
            cover = absolute_url(url, cover)
        return {
            "title": title_node.get_text(" ", strip=True),
            "summary": summary_node.get_text(" ", strip=True) if summary_node else "",
            "cover": cover,
            "id": manga_id.group(1) if manga_id else "",
            "latest_chapter": latest,
            "post_url": url,
        }
    except Exception:
        return "not found"

async def gmanga_chapter_imgs(chapter_url):
    try:
        text = await fetch_text(chapter_url, headers=_HEADERS)
        soup = BeautifulSoup(text, "html.parser")
        images = extract_image_urls(soup, base_url=chapter_url)
        return [
            url for url in images
            if "avatar" not in url.lower() and "logo" not in url.lower()
        ]
    except Exception:
        return []

async def gmanga_chapters(post_url, *, min_chapter=None):
    if not post_url:
        return None
    try:
        text = await fetch_text(f"{post_url.rstrip('/')}/ajax/chapters/", method="POST", headers=_HEADERS)
        soup = BeautifulSoup(text, "html.parser")
        chapters_info = {}
        for chapter in soup.select("li.wp-manga-chapter"):
            link = chapter.find("a")
            if not link:
                continue
            number = chapter_number(link.get_text(" ", strip=True), href=link.get("href"))
            chapter_url = absolute_url(post_url, link.get("href"))
            if number is None or not chapter_url:
                continue
            release = chapter.select_one(".chapter-release-date i, .chapter-release-date")
            release_date = date.convert_arabic_date_to_numeric(release.get_text(" ", strip=True).replace("،", "")) if release else ""
            chapters_info[number] = {
                "chapter": number,
                "chapter_url": chapter_url,
                "teams": [{"team_name": "gmanga", "chapter_date": release_date, "chapter_page": []}],
            }

        urls = [
            item["chapter_url"] for item in chapters_info.values()
            if min_chapter is None or item["chapter"] > min_chapter
        ]
        pages = await gather_limited([gmanga_chapter_imgs(url) for url in urls], limit=6, return_exceptions=True)
        for item, value in zip((item for item in chapters_info.values() if min_chapter is None or item["chapter"] > min_chapter), pages):
            item["teams"][0]["chapter_page"] = value if isinstance(value, list) else []

        for item in chapters_info.values():
            item.pop("chapter_url", None)
        return list(chapters_info.values())
    except Exception:
        return None
