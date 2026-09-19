import re
import sys
from os import path
from urllib.parse import urlencode

from bs4 import BeautifulSoup

sys.path.append(path.dirname(path.dirname(path.abspath(__file__))))

from MangaSite.http import fetch_text
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


async def gmanga_search(name):
    url = "https://gmanga.site/wp-admin/admin-ajax.php"
    payload = {"title": name, "action": "wp-manga-search-manga"}
    try:
        import json
        response = await fetch_text(url, method="POST", data=payload, headers=_HEADERS)
        data = json.loads(response)
        manga_list = data.get("data") or []
        if manga_list:
            return await gmanga_info(manga_list[0].get("url"))
    except Exception:
        pass

    fallback_url = await _gmanga_html_search(name)
    return await gmanga_info(fallback_url) if fallback_url else "not found"


async def gmanga_latest_chapters(post_url):
    try:
        response_text = await fetch_text(
            f"{post_url.rstrip('/')}/ajax/chapters/",
            method="POST",
            headers=_HEADERS,
        )
        soup = BeautifulSoup(response_text, "html.parser")
        chapter = soup.find("li", class_="wp-manga-chapter")
        if not chapter or not chapter.a:
            return None
        match = re.search(r"\d+(?:\.\d+)?", chapter.a.get_text(" ", strip=True))
        return float(match.group()) if match else None
    except Exception:
        return None


async def gmanga_info(url):
    if not url:
        return "not found"
    try:
        response_text = await fetch_text(url, method="GET", headers=_HEADERS)
        soup = BeautifulSoup(response_text, "html.parser")
        title_node = soup.select_one(".post-title h1")
        summary_node = soup.select_one(".summary__content")
        image_node = soup.select_one(".summary_image img")
        manga_id = re.search(r'"manga_id"\s*:\s*"?([0-9]+)', response_text)
        if not title_node:
            return "not found"

        latest = await gmanga_latest_chapters(url)
        return {
            "title": title_node.get_text(strip=True),
            "summary": summary_node.get_text(" ", strip=True) if summary_node else "",
            "cover": (image_node.get("data-src") or image_node.get("src", "")) if image_node else "",
            "id": manga_id.group(1) if manga_id else "",
            "latest_chapter": latest,
            "post_url": url,
        }
    except Exception:
        return "not found"


async def gmanga_chapter_imgs(chapter_url):
    try:
        response_text = await fetch_text(chapter_url, headers=_HEADERS)
        soup = BeautifulSoup(response_text, "html.parser")
        images = []
        for div in soup.select("div.page-break"):
            image = div.find("img")
            if image:
                src = image.get("data-src") or image.get("src")
                if src:
                    images.append(src.strip())
        return images
    except Exception:
        return []


async def gmanga_chapters(post_url, *, min_chapter=None):
    if not post_url:
        return None
    try:
        response_text = await fetch_text(
            f"{post_url.rstrip('/')}/ajax/chapters/",
            method="POST",
            headers=_HEADERS,
        )
        soup = BeautifulSoup(response_text, "html.parser")
        chapters_info = {}
        for chapter in soup.select("li.wp-manga-chapter"):
            link = chapter.find("a")
            if not link:
                continue
            match = re.search(r"\d+(?:\.\d+)?", link.get_text(" ", strip=True))
            if not match:
                continue
            chapter_num = float(match.group())
            if chapter_num.is_integer():
                chapter_num = int(chapter_num)
            chapter_url = link.get("href")
            if not chapter_url:
                continue
            release = chapter.select_one(".chapter-release-date i, .chapter-release-date")
            release_date = date.convert_arabic_date_to_numeric(
                release.get_text(" ", strip=True).replace("،", "")
            ) if release else ""
            chapters_info[(chapter_num, "gmanga")] = {
                "chapter": chapter_num,
                "teams": [{
                    "team_name": "gmanga",
                    "chapter_date": release_date,
                    "chapter_page": (await gmanga_chapter_imgs(chapter_url) if min_chapter is None or chapter_num > min_chapter else []),
                }],
            }
        return list(chapters_info.values())
    except Exception:
        return None
