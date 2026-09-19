import re
import sys
from os import path

import cloudscraper
from bs4 import BeautifulSoup

sys.path.append(path.dirname(path.dirname(path.abspath(__file__))))

from utils import date


BASE_URL = "https://scarmanga.com"


def _scraper():
    return cloudscraper.create_scraper(browser={"browser": "firefox", "platform": "windows", "mobile": False})


def _get(scraper, url):
    response = scraper.get(url, timeout=20)
    response.raise_for_status()
    return response.text


def get_aresnov_summary(post_url):
    try:
        html = _get(_scraper(), post_url)
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
        info = get_aresnov_summary(post_url)
        try:
            latest = float(item.get("post_latest", 0))
            if latest.is_integer():
                latest = int(latest)
        except (ValueError, TypeError):
            latest = 0
        return {
            "title": item.get("post_title", name),
            "summary": info[3],
            "cover": item.get("post_image", ""),
            "id": item.get("ID"),
            "latest_chapter": latest,
            "alternative_title": info[4],
            "post_url": post_url,
        }
    except Exception:
        return "not found"


def aresnov_chapter_imgs(url):
    try:
        html = _get(_scraper(), url)
        soup = BeautifulSoup(html, "html.parser")
        images = []
        for image in soup.select("img[decoding='async'][src], .reading-content img[src]"):
            src = image.get("src")
            if src and src not in images:
                images.append(src.strip())
        return images
    except Exception:
        return []


def get_aresnov_chapters(name, *, min_chapter=None)
    try:
        html = _get(_scraper(), f"{BASE_URL}/series/{name}")
        soup = BeautifulSoup(html, "html.parser")
        chapters_info = {}
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
            release_date = date.convert_arabic_date_to_numeric(date_node.get_text(" ", strip=True)) if date_node else ""
            chapters_info[(chapter_num, "Aresnov")] = {
                "chapter": chapter_num,
                "teams": [{"team_name": "Aresnov", "chapter_date": release_date, "chapter_page": (aresnov_chapter_imgs(chapter_url) if min_chapter is None or chapter_num > min_chapter else [])}],
            }
        return list(chapters_info.values())
    except Exception:
        return None
