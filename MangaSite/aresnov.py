import re
import sys
from concurrent.futures import ThreadPoolExecutor
from os import path

import cloudscraper
from bs4 import BeautifulSoup

sys.path.append(path.dirname(path.dirname(path.abspath(__file__))))

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
        html = _get(scraper, post_url)
        soup = BeautifulSoup(html, "html.parser")
        alternative = soup.select_one("span.alternative")
        description = soup.select_one(".description")
        return (
            None,
            None,
            None,
            description.get_text(" ", strip=True) if description else "",
            alternative.get_text(" ", strip=True) if alternative else None,
        )
    except Exception:
        return None, None, None, "", None


def get_aresnov_info(name):
    try:
        scraper = _scraper()
        response = scraper.post(
            f"{BASE_URL}/wp-admin/admin-ajax.php",
            data={"action": "ts_ac_do_search", "ts_ac_query": name},
            timeout=4,
        )
        response.raise_for_status()
        data = response.json()
        series = ((data.get("series") or [{}])[0]).get("all") or []
        if not series:
            return "not found"
        item = series[0]
        post_url = item.get("post_link")
        if not post_url:
            return "not found"
        html = _get(scraper, post_url)
        soup = BeautifulSoup(html, "html.parser")
        alternative = soup.select_one("span.alternative")
        description = soup.select_one(".description")
        try:
            latest = float(item.get("post_latest", 0))
            if latest.is_integer():
                latest = int(latest)
        except (ValueError, TypeError):
            latest = 0
        return {
            "title": item.get("post_title", name),
            "summary": description.get_text(" ", strip=True) if description else "",
            "cover": item.get("post_image", ""),
            "id": item.get("ID"),
            "latest_chapter": latest,
            "alternative_title": alternative.get_text(" ", strip=True) if alternative else None,
            "post_url": post_url,
        }
    except Exception:
        return "not found"


def aresnov_chapter_imgs(url, *, scraper=None):
    try:
        own_scraper = scraper or _scraper()
        html = _get(own_scraper, url)
        soup = BeautifulSoup(html, "html.parser")
        images = []
        for image in soup.select("img[decoding='async'][src], .reading-content img[src]"):
            src = image.get("src")
            if src and src.strip() not in images:
                images.append(src.strip())
        return images
    except Exception:
        return []


def get_aresnov_chapters(name, *, min_chapter=None):
    try:
        scraper = _scraper()
        html = _get(scraper, f"{BASE_URL}/series/{name}")
        soup = BeautifulSoup(html, "html.parser")
        chapters_info = {}
        chapter_tasks = []

        for link in soup.select("a[href]"):
            number_node = link.select_one(".chapternum")
            date_node = link.select_one(".chapterdate")
            if not number_node:
                continue

            match = re.search(r"\d+(?:\.\d+)?", number_node.get_text(" ", strip=True))
            if not match:
                continue

            chapter_num = float(match.group())
            if chapter_num.is_integer():
                chapter_num = int(chapter_num)

            chapter_url = link.get("href")
            if not chapter_url:
                continue

            release_date = (
                date.convert_arabic_date_to_numeric(
                    date_node.get_text(" ", strip=True)
                )
                if date_node
                else ""
            )
            key = (chapter_num, "Aresnov")
            if key in chapters_info:
                continue

            chapters_info[key] = {
                "chapter": chapter_num,
                "teams": [{
                    "team_name": "Aresnov",
                    "chapter_date": release_date,
                    "chapter_page": [],
                }],
            }

            if min_chapter is None or chapter_num > min_chapter:
                chapter_tasks.append((chapter_num, chapter_url))

        if chapter_tasks:
            def fetch_pages(item):
                chapter_num, chapter_url = item
                return chapter_num, aresnov_chapter_imgs(chapter_url, scraper=scraper)

            with ThreadPoolExecutor(max_workers=CHAPTER_CONCURRENCY) as executor:
                for chapter_num, pages in executor.map(fetch_pages, chapter_tasks):
                    key = (chapter_num, "Aresnov")
                    chapters_info[key]["teams"][0]["chapter_page"] = pages

        return list(chapters_info.values())
    except Exception:
        return None
