import datetime
import re
import sys
from os import path
from urllib.parse import quote

from bs4 import BeautifulSoup

sys.path.append(path.dirname(path.dirname(path.abspath(__file__))))

from MangaSite.http import fetch_text


_HEADERS = {"Accept": "text/html,application/json,*/*", "X-Requested-With": "XMLHttpRequest"}


async def teamXnovel_summary(post_url):
    try:
        text = await fetch_text(post_url, headers=_HEADERS)
        soup = BeautifulSoup(text, "html.parser")
        node = soup.select_one(".review-content p")
        summary = node.get_text(" ", strip=True) if node else ""
        links = []
        pagination = soup.select_one("ul.pagination")
        if pagination:
            for link in pagination.select("a[href]"):
                href = link.get("href")
                if href:
                    match = re.search(r"[?&](?:page|paged)=(\d+)", href)
                    if match:
                        links.append((int(match.group(1)), href))
            links = [href for _, href in sorted(set(links))]
        return summary, links or [post_url]
    except Exception:
        return "", [post_url]


async def teamXnovel_info(name):
    try:
        url = f"https://teamxnovel.com/ajax/search?keyword={quote(name)}"
        response = await fetch_text(url, headers=_HEADERS)
        return {"respons": response}
    except Exception:
        return {"respons": ""}


async def teamXnovel_chapter_imgs(chapter_url):
    try:
        text = await fetch_text(chapter_url, headers=_HEADERS)
        soup = BeautifulSoup(text, "html.parser")
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


async def teamXnovel_chapters(pages):
    if isinstance(pages, str):
        pages = [pages]
    chapters_info = {}
    try:
        for page in pages:
            text = await fetch_text(page, headers=_HEADERS)
            soup = BeautifulSoup(text, "html.parser")
            for chapter in soup.select("li"):
                number_node = chapter.select_one(".epl-num")
                link = chapter.find("a", href=True)
                if not number_node or not link:
                    continue
                match = re.search(r"\d+(?:\.\d+)?", number_node.get_text(" ", strip=True))
                if not match:
                    continue
                chapter_num = float(match.group())
                if chapter_num.is_integer():
                    chapter_num = int(chapter_num)
                date_node = chapter.select_one(".epl-date")
                raw_date = date_node.get_text(" ", strip=True) if date_node else ""
                try:
                    release_date = datetime.datetime.strptime(raw_date, "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d")
                except ValueError:
                    release_date = raw_date[:10] if len(raw_date) >= 10 else raw_date
                chapters_info[(chapter_num, "TeamXnovel")] = {
                    "chapter": chapter_num,
                    "teams": [{"team_name": "TeamXnovel", "chapter_date": release_date, "chapter_page": await teamXnovel_chapter_imgs(link["href"])}],
                }
        return list(chapters_info.values())
    except Exception:
        return None
