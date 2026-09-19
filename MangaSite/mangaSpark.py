import re
from os import path
import sys
from urllib.parse import urlencode

from bs4 import BeautifulSoup

sys.path.append(path.dirname(path.dirname(path.abspath(__file__))))

from MangaSite.http import fetch_json, fetch_text
from utils import date


BASE_URL = "https://mangaspark.org/wp-admin/admin-ajax.php"
HEADERS = {
    "accept": "application/json, text/javascript, */*; q=0.01",
    "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
    "x-requested-with": "XMLHttpRequest",
}


def _chapter_number(value):
    match = re.search(r"\d+(?:\.\d+)?", str(value or ""))
    if not match:
        return None
    number = float(match.group())
    return int(number) if number.is_integer() else number


def _search_url(name):
    return "https://mangaspark.org/?" + urlencode({"s": name, "post_type": "wp-manga"})


async def _mangaspark_html_search(name):
    try:
        text = await fetch_text(_search_url(name), headers=HEADERS)
        soup = BeautifulSoup(text, "html.parser")
        link = soup.select_one(
            ".c-tabs-item__content .post-title a, "
            ".c-tabs-item__content .tab-thumb a, "
            ".row.c-tabs-item__content .post-title a"
        )
        return link.get("href") if link else None
    except Exception:
        return None


async def mangaspark_search(name):
    try:
        data = await fetch_json(BASE_URL, method="POST", data={
            "action": "wp-manga-search-manga",
            "title": name,
        }, headers=HEADERS)
        items = data.get("data") or []
        if items:
            result = await mangaspark_info(items[0].get("url"))
            if result != "not found":
                return result
    except Exception:
        pass

    fallback_url = await _mangaspark_html_search(name)
    return await mangaspark_info(fallback_url) if fallback_url else "not found"


async def mangaspark_latest_chapters(manga_id):
    try:
        response_text = await fetch_text(BASE_URL, method="POST", data={
            "action": "manga_get_chapters",
            "manga": manga_id,
        }, headers=HEADERS)
        soup = BeautifulSoup(response_text, "html.parser")
        chapter = soup.select_one("li.wp-manga-chapter a")
        return _chapter_number(chapter.get_text(" ", strip=True)) if chapter else None
    except Exception:
        return None


async def mangaspark_info(url):
    if not url:
        return "not found"
    try:
        response_text = await fetch_text(url, headers=HEADERS)
        soup = BeautifulSoup(response_text, "html.parser")
        title_node = soup.select_one(".post-title h1")
        description_node = soup.select_one(".description-summary")
        image_node = soup.select_one('meta[property="og:image"]')
        manga_id = re.search(r'"manga_id"\s*:\s*"?([0-9]+)', response_text)

        if not title_node:
            return "not found"

        latest = await mangaspark_latest_chapters(manga_id.group(1)) if manga_id else None
        return {
            "title": title_node.get_text(strip=True),
            "summary": description_node.get_text(" ", strip=True) if description_node else "",
            "cover": image_node.get("content", "") if image_node else "",
            "id": manga_id.group(1) if manga_id else "",
            "latest_chapter": latest,
        }
    except Exception:
        return "not found"


async def mangaspark_chapter_imgs(url):
    try:
        response_text = await fetch_text(url)
        soup = BeautifulSoup(response_text, "html.parser")
        images = []
        for image in soup.select("div.page-break img"):
            src = image.get("data-src") or image.get("src")
            if src:
                images.append(src.strip())
        return images
    except Exception:
        return []


async def mangaspark_chapters(manga_id, *, min_chapter=None):
    try:
        response_text = await fetch_text(BASE_URL, method="POST", data={
            "action": "manga_get_chapters",
            "manga": manga_id,
        }, headers=HEADERS)
        soup = BeautifulSoup(response_text, "html.parser")
        chapters_info = {}

        for chapter in soup.select("li.wp-manga-chapter"):
            link = chapter.find("a")
            if not link:
                continue
            chapter_num = _chapter_number(link.get_text(" ", strip=True))
            chapter_url = link.get("href")
            if chapter_num is None or not chapter_url:
                continue

            release = chapter.select_one(".chapter-release-date i, .chapter-release-date")
            release_text = release.get_text(" ", strip=True) if release else ""
            chapters_info[(chapter_num, "MangaSpark")] = {
                "chapter": chapter_num,
                "teams": [{
                    "team_name": "MangaSpark",
                    "chapter_date": date.convert_arabic_date_to_numeric(release_text),
                    "chapter_page": (await mangaspark_chapter_imgs(chapter_url) if min_chapter is None or chapter_num > min_chapter else []),
                }],
            }

        return list(chapters_info.values())
    except Exception:
        return None
