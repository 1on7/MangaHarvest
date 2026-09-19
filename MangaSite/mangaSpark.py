import re
import sys
from os import path
from urllib.parse import urlencode

from bs4 import BeautifulSoup

sys.path.append(path.dirname(path.dirname(path.abspath(__file__))))

from MangaSite.http import fetch_json, fetch_text, gather_limited
from MangaSite.parser_utils import absolute_url, best_match, chapter_number, extract_image_urls
from utils import date

BASE_URL = "https://mangaspark.org/wp-admin/admin-ajax.php"
HEADERS = {
    "accept": "application/json, text/javascript, */*; q=0.01",
    "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
    "x-requested-with": "XMLHttpRequest",
}

async def _mangaspark_html_search(name):
    try:
        soup = BeautifulSoup(await fetch_text("https://mangaspark.org/?" + urlencode({"s": name, "post_type": "wp-manga"}), headers=HEADERS), "html.parser")
        items = [
            {"title": link.get_text(" ", strip=True), "url": link.get("href")}
            for link in soup.select(".c-tabs-item__content .post-title a, .c-tabs-item__content .tab-thumb a, .row.c-tabs-item__content .post-title a")
            if link.get("href")
        ]
        item = best_match(items, name)
        return item.get("url") if item else None
    except Exception:
        return None

async def mangaspark_search(name):
    try:
        data = await fetch_json(BASE_URL, method="POST", data={"action": "wp-manga-search-manga", "title": name}, headers=HEADERS)
        item = best_match(data.get("data") or [], name)
        if item and item.get("url"):
            result = await mangaspark_info(item["url"])
            if result != "not found":
                return result
    except Exception:
        pass
    fallback_url = await _mangaspark_html_search(name)
    return await mangaspark_info(fallback_url) if fallback_url else "not found"

async def mangaspark_latest_chapters(manga_id):
    try:
        soup = BeautifulSoup(await fetch_text(BASE_URL, method="POST", data={"action": "manga_get_chapters", "manga": manga_id}, headers=HEADERS), "html.parser")
        link = soup.select_one("li.wp-manga-chapter a")
        return chapter_number(link.get_text(" ", strip=True), href=link.get("href")) if link else None
    except Exception:
        return None

async def mangaspark_info(url):
    if not url:
        return "not found"
    try:
        text = await fetch_text(url, headers=HEADERS)
        soup = BeautifulSoup(text, "html.parser")
        title_node = soup.select_one(".post-title h1")
        description_node = soup.select_one(".description-summary")
        image_node = soup.select_one('meta[property="og:image"]')
        manga_id = re.search(r'"manga_id"\s*:\s*"?(\d+)', text)
        if not title_node:
            return "not found"
        return {
            "title": title_node.get_text(" ", strip=True),
            "summary": description_node.get_text(" ", strip=True) if description_node else "",
            "cover": absolute_url(url, image_node.get("content", "")) if image_node else "",
            "id": manga_id.group(1) if manga_id else "",
            "latest_chapter": await mangaspark_latest_chapters(manga_id.group(1)) if manga_id else None,
        }
    except Exception:
        return "not found"

async def mangaspark_chapter_imgs(url):
    try:
        soup = BeautifulSoup(await fetch_text(url), "html.parser")
        return extract_image_urls(soup, base_url=url)
    except Exception:
        return []

async def mangaspark_chapters(manga_id, *, min_chapter=None):
    if not manga_id:
        return None
    try:
        soup = BeautifulSoup(await fetch_text(BASE_URL, method="POST", data={"action": "manga_get_chapters", "manga": manga_id}, headers=HEADERS), "html.parser")
        chapters_info = {}
        for chapter in soup.select("li.wp-manga-chapter"):
            link = chapter.find("a")
            if not link:
                continue
            number = chapter_number(link.get_text(" ", strip=True), href=link.get("href"))
            chapter_url = absolute_url("https://mangaspark.org/", link.get("href"))
            if number is None or not chapter_url:
                continue
            release = chapter.select_one(".chapter-release-date i, .chapter-release-date")
            release_text = release.get_text(" ", strip=True) if release else ""
            chapters_info[number] = {
                "chapter": number,
                "chapter_url": chapter_url,
                "teams": [{"team_name": "MangaSpark", "chapter_date": date.convert_arabic_date_to_numeric(release_text), "chapter_page": []}],
            }
        selected = [item for item in chapters_info.values() if min_chapter is None or item["chapter"] > min_chapter]
        pages = await gather_limited([mangaspark_chapter_imgs(item["chapter_url"]) for item in selected], limit=6, return_exceptions=True)
        for item, value in zip(selected, pages):
            item["teams"][0]["chapter_page"] = value if isinstance(value, list) else []
        for item in chapters_info.values():
            item.pop("chapter_url", None)
        return list(chapters_info.values())
    except Exception:
        return None
