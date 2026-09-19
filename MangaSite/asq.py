import html
import re
import sys
from os import path
from urllib.parse import urlencode

from bs4 import BeautifulSoup

sys.path.append(path.dirname(path.dirname(path.abspath(__file__))))

from MangaSite.http import fetch_json, fetch_text
from utils import date


_HEADERS = {"Accept": "text/html,application/json,*/*", "X-Requested-With": "XMLHttpRequest"}


def _search_url(name):
    return "https://3asq.org/?" + urlencode({"s": name, "post_type": "wp-manga"})


async def _asq_html_search(name):
    try:
        text = await fetch_text(_search_url(name), headers=_HEADERS)
        soup = BeautifulSoup(text, "html.parser")
        link = soup.select_one(
            ".c-tabs-item__content .post-title a, "
            ".c-tabs-item__content .tab-thumb a, "
            ".row.c-tabs-item__content .post-title a"
        )
        if not link:
            return None
        return link.get("href")
    except Exception:
        return None


async def asq_latest_chapters(post_url):
    try:
        text = await fetch_text(post_url, headers=_HEADERS)
        soup = BeautifulSoup(text, "html.parser")
        image = soup.select_one(".summary_image img")
        excerpt = soup.select_one(".post-content p")
        chapter = soup.select_one("li.wp-manga-chapter a")
        latest = None
        if chapter:
            match = re.search(r"\d+(?:\.\d+)?", chapter.get_text(" ", strip=True))
            if match:
                latest = float(match.group())
        return latest, image.get("src", "") if image else "", html.unescape(excerpt.get_text(" ", strip=True)) if excerpt else ""
    except Exception:
        return None


async def asq_info(name):
    try:
        data = await fetch_json(
            "https://3asq.org/wp-admin/admin-ajax.php",
            method="POST",
            data={"action": "wp-manga-search-manga", "title": name},
            headers=_HEADERS,
        )
        items = data.get("data") or []
        if items:
            item = items[0]
            post_url = item.get("url")
            if post_url:
                info = await asq_latest_chapters(post_url)
                latest, cover, summary = info if info else (None, "", "")
                return {
                    "title": item.get("title", name),
                    "summary": summary,
                    "cover": cover,
                    "id": 0,
                    "latest_chapter": latest,
                    "post_url": post_url,
                }
    except Exception:
        pass

    post_url = await _asq_html_search(name)
    if not post_url:
        return "not found"

    info = await asq_latest_chapters(post_url)
    latest, cover, summary = info if info else (None, "", "")
    title_node = None
    try:
        text = await fetch_text(post_url, headers=_HEADERS)
        soup = BeautifulSoup(text, "html.parser")
        title_node = soup.select_one(".post-title h1")
    except Exception:
        pass

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
        text = await fetch_text(chapter_url, headers=_HEADERS)
        soup = BeautifulSoup(text, "html.parser")
        return [
            src.strip()
            for div in soup.select("div.page-break")
            if (img := div.find("img")) and (src := (img.get("data-src") or img.get("src")))
        ]
    except Exception:
        return []


async def asq_chapters(post_url, *, min_chapter=None)
    try:
        text = await fetch_text(post_url, headers=_HEADERS)
        soup = BeautifulSoup(text, "html.parser")
        chapters_info = {}
        for chapter in soup.select("li.wp-manga-chapter"):
            link = chapter.find("a")
            if not link:
                continue
            match = re.search(r"\d+(?:\.\d+)?", link.get_text(" ", strip=True))
            if not match:
                continue
            number = float(match.group())
            if number.is_integer():
                number = int(number)
            release = chapter.select_one(".chapter-release-date i, .chapter-release-date")
            release_date = date.convert_arabic_date_to_numeric(
                release.get_text(" ", strip=True).replace("،", "")
            ) if release else ""
            chapters_info[(number, "asq")] = {
                "chapter": number,
                "teams": [{
                    "team_name": "asq",
                    "chapter_date": release_date,
                    "chapter_page": (await asq_chapter_imgs(link.get("href")) if min_chapter is None or number > min_chapter else []),
                }],
            }
        return list(chapters_info.values())
    except Exception:
        return None
