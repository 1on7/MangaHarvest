import re
import sys
from concurrent.futures import ThreadPoolExecutor
from os import path
from urllib.parse import urljoin

import cloudscraper
from bs4 import BeautifulSoup

sys.path.append(path.dirname(path.dirname(path.abspath(__file__))))

from MangaSite.parser_utils import chapter_number, extract_image_urls
from utils import date

BASE_URL = "https://scarmanga.com"
CHAPTER_CONCURRENCY = 4

def _scraper():
    return cloudscraper.create_scraper(
        browser={"browser": "firefox", "platform": "windows", "mobile": False}
    )

def _get(scraper, url, *, timeout=20):
    response = scraper.get(url, timeout=timeout)
    response.raise_for_status()
    return response.text

def get_aresnov_summary(post_url):
    try:
        scraper = _scraper()
        soup = BeautifulSoup(_get(scraper, post_url), "html.parser")
        alternative = soup.select_one("span.alternative")
        description = soup.select_one(".description")
        return (None, None, None, description.get_text(" ", strip=True) if description else "", alternative.get_text(" ", strip=True) if alternative else None)
    except Exception:
        return None, None, None, "", None

def get_aresnov_info(name):
    try:
        scraper = _scraper()
        response = scraper.post(
            f"{BASE_URL}/wp-admin/admin-ajax.php",
            data={"action": "ts_ac_do_search", "ts_ac_query": name},
            timeout=6,
        )
        response.raise_for_status()
        data = response.json()
        series = ((data.get("series") or [{}])[0]).get("all") or []
        if not series:
            return "not found"

        # Search endpoint is weakly ordered, so rank all returned titles.
        scored = []
        for item in series:
            title = item.get("post_title") or ""
            score = __import__("utils.title", fromlist=["title_similarity"]).title_similarity(name, title)
            scored.append((score, item))
        item = max(scored, key=lambda pair: pair[0])[1]
        post_url = item.get("post_link")
        if not post_url:
            return "not found"

        soup = BeautifulSoup(_get(scraper, post_url), "html.parser")
        alternative = soup.select_one("span.alternative")
        description = soup.select_one(".description")
        latest = chapter_number(item.get("post_latest"))
        return {
            "title": item.get("post_title", name),
            "summary": description.get_text(" ", strip=True) if description else "",
            "cover": item.get("post_image", ""),
            "id": item.get("ID"),
            "latest_chapter": latest if latest is not None else 0,
            "alternative_title": alternative.get_text(" ", strip=True) if alternative else None,
            "post_url": post_url,
        }
    except Exception:
        return "not found"

def aresnov_chapter_imgs(url, *, scraper=None):
    try:
        own_scraper = scraper or _scraper()
        soup = BeautifulSoup(_get(own_scraper, url), "html.parser")
        return extract_image_urls(soup, base_url=url)
    except Exception:
        return []

def get_aresnov_chapters(name, *, min_chapter=None):
    try:
        scraper = _scraper()
        soup = BeautifulSoup(_get(scraper, f"{BASE_URL}/series/{name}"), "html.parser")
        chapters_info = {}
        chapter_tasks = []

        for link in soup.select("a[href]"):
            number_node = link.select_one(".chapternum")
            if not number_node:
                continue
            chapter_url = urljoin(BASE_URL, link.get("href") or "")
            number = chapter_number(number_node.get_text(" ", strip=True), href=chapter_url)
            if number is None or not chapter_url:
                continue

            date_node = link.select_one(".chapterdate")
            release_date = date.convert_arabic_date_to_numeric(date_node.get_text(" ", strip=True)) if date_node else ""
            chapters_info[number] = {
                "chapter": number,
                "teams": [{"team_name": "Aresnov", "chapter_date": release_date, "chapter_page": []}],
            }
            if min_chapter is None or number > min_chapter:
                chapter_tasks.append((number, chapter_url))

        if chapter_tasks:
            def fetch_pages(item):
                chapter_num, chapter_url = item
                return chapter_num, aresnov_chapter_imgs(chapter_url, scraper=scraper)

            with ThreadPoolExecutor(max_workers=CHAPTER_CONCURRENCY) as executor:
                for chapter_num, pages in executor.map(fetch_pages, chapter_tasks):
                    if chapter_num in chapters_info:
                        chapters_info[chapter_num]["teams"][0]["chapter_page"] = pages

        return list(chapters_info.values())
    except Exception:
        return None
