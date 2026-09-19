import html
import sys
from os import path
from urllib.parse import urlencode

from bs4 import BeautifulSoup

sys.path.append(path.dirname(path.dirname(path.abspath(__file__))))

from MangaSite.http import fetch_json, fetch_text, gather_limited
from MangaSite.parser_utils import absolute_url, best_match, chapter_number, extract_image_urls
from utils import date

_HEADERS = {"Accept": "text/html,application/json,*/*", "X-Requested-With": "XMLHttpRequest"}

def _search_url(name):
    return "https://3asq.org/?" + urlencode({"s": name, "post_type": "wp-manga"})

async def _asq_html_search(name):
    try:
        text = await fetch_text(_search_url(name), headers=_HEADERS)
        soup = BeautifulSoup(text, "html.parser")
        items = [
            {"title": link.get_text(" ", strip=True), "url": link.get("href")}
            for link in soup.select(".c-tabs-item__content .post-title a, .c-tabs-item__content .tab-thumb a, .row.c-tabs-item__content .post-title a")
            if link.get("href")
        ]
        item = best_match(items, name)
        return item.get("url") if item else None
    except Exception:
        return None

async def asq_latest_chapters(post_url):
    try:
        text = await fetch_text(post_url, headers=_HEADERS)
        soup = BeautifulSoup(text, "html.parser")
        image = soup.select_one(".summary_image img")
        excerpt = soup.select_one(".post-content p")
        chapter = soup.select_one("li.wp-manga-chapter a")
        latest = chapter_number(chapter.get_text(" ", strip=True), href=chapter.get("href")) if chapter else None
        cover = absolute_url(post_url, (image.get("data-src") or image.get("data-lazy-src") or image.get("src")) if image else "")
        return latest, cover, html.unescape(excerpt.get_text(" ", strip=True)) if excerpt else ""
    except Exception:
        return None, "", ""

async def asq_info(name):
    try:
        data = await fetch_json(
            "https://3asq.org/wp-admin/admin-ajax.php",
            method="POST",
            data={"action": "wp-manga-search-manga", "title": name},
            headers=_HEADERS,
        )
        item = best_match(data.get("data") or [], name)
        if item and item.get("url"):
            latest, cover, summary = await asq_latest_chapters(item["url"])
            return {
                "title": item.get("title", name),
                "summary": summary,
                "cover": cover,
                "id": 0,
                "latest_chapter": latest,
                "post_url": item["url"],
            }
    except Exception:
        pass

    post_url = await _asq_html_search(name)
    if not post_url:
        return "not found"
    latest, cover, summary = await asq_latest_chapters(post_url)
    try:
        text = await fetch_text(post_url, headers=_HEADERS)
        soup = BeautifulSoup(text, "html.parser")
        title_node = soup.select_one(".post-title h1")
    except Exception:
        title_node = None
    return {
        "title": title_node.get_text(" ", strip=True) if title_node else name,
        "summary": summary,
        "cover": cover,
        "id": 0,
        "latest_chapter": latest,
        "post_url": post_url,
    }

async def asq_chapter_imgs(chapter_url):
    try:
        soup = BeautifulSoup(await fetch_text(chapter_url, headers=_HEADERS), "html.parser")
        return extract_image_urls(soup, base_url=chapter_url)
    except Exception:
        return []

async def asq_chapters(post_url, *, min_chapter=None):
    try:
        soup = BeautifulSoup(await fetch_text(post_url, headers=_HEADERS), "html.parser")
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
                "teams": [{"team_name": "asq", "chapter_date": release_date, "chapter_page": []}],
            }

        selected = [item for item in chapters_info.values() if min_chapter is None or item["chapter"] > min_chapter]
        pages = await gather_limited([asq_chapter_imgs(item["chapter_url"]) for item in selected], limit=6, return_exceptions=True)
        for item, value in zip(selected, pages):
            item["teams"][0]["chapter_page"] = value if isinstance(value, list) else []
        for item in chapters_info.values():
            item.pop("chapter_url", None)
        return list(chapters_info.values())
    except Exception:
        return None
