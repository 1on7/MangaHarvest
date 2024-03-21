import asyncio
from aiohttp import ClientSession, ClientTimeout
from bs4 import BeautifulSoup
import re
import json
import time

async def fetch(url, method='GET', data=None, headers=None):
    async with ClientSession(timeout=ClientTimeout(total=30)) as session:
        if method == 'GET':
            async with session.get(url, headers=headers) as response:
                return await response.text()
        elif method == 'POST':
            async with session.post(url, json=data, headers=headers) as response:
                return await response.text()
        else:
            raise ValueError(f"Invalid HTTP method: {method}")

async def get_gmanga_info(name):
    url = 'https://api.gmanga.me/api/quick_search'
    payload = {'query': name, 'includes': ['Manga']}
    headers = {
        'content-type': 'application/json',
        'sec-ch-ua': '"Not A(Brand";v="99", "Opera";v="107", "Chromium";v="121"',
        'sec-ch-ua-arch': '"x86"',
        'sec-ch-ua-bitness': '"64"',
        'sec-ch-ua-full-version': '"107.0.5045.21"',
        'sec-ch-ua-full-version-list': '"Not A(Brand";v="99.0.0.0", "Opera";v="107.0.5045.21", "Chromium";v="121.0.6167.160"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-model': '""',
        'sec-ch-ua-platform': '"Windows"',
        'sec-ch-ua-platform-version': '"10.0.0"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
        'x-requested-with': 'XMLHttpRequest',
        'referrer': 'https://gmanga.me/'
    }

    response_text = await fetch(url, method='POST', data=payload, headers=headers)
    data = json.loads(response_text)
    if data:
        manga_data = data[0]["data"]
        if manga_data:
            manga_info = manga_data[0]
            title = manga_info.get('title')
            summary = manga_info.get('summary').replace("\n", "").replace('"', "'")
            cover_url = f"https://media.gmanga.me/uploads/manga/cover/{manga_info.get('id')}/{manga_info.get('cover')}"
            manga_id = manga_info.get('id')
            latest_chapter = float(manga_info.get('latest_chapter'))
            return {"title": title, "summary": summary, "cover": cover_url, "id": manga_id, "latest_chapter": latest_chapter}
        else:
            return "not found"
    else:
        return "Error"

async def get_gmanga_chapter_imgs(chapter_url):
    response_text = await fetch(chapter_url)
    pattern = r'g"],(.*?),"file'
    match = re.search(pattern, response_text, re.DOTALL)
    if match:
        webp_pages = "{" + match.group(1) + "}"
        webp_pages = json.loads(webp_pages)
        webp_url = []
        if webp_pages:
            storage_key = webp_pages.get("storage_key")
            for webp_page in webp_pages["webp_pages"]:
                webp_url.append(f"https://media.gmanga.me/uploads/releases/{storage_key}/mq_webp/{webp_page}")
            return webp_url
    else:
        return None

async def get_gmanga_chapters(id, name):
    url = f"https://api2.gmanga.me/api/mangas/{id}/releases"
    headers = {
        "content-type": "application/json",
        "sec-ch-ua": "\"Not A(Brand\";v=\"99\", \"Chrome\";v=\"107\", \"Chromium\";v=\"121\"",
        "sec-ch-ua-arch": "\"x86\"",
        "sec-ch-ua-bitness": "\"64\"",
        "sec-ch-ua-full-version": "\"107.0.5045.21\"",
        "sec-ch-ua-full-version-list": "\"Not A(Brand\";v=\"99.0.0.0\", \"Chrome\";v=\"107.0.5045.21\", \"Chromium\";v=\"121.0.6167.160\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-model": "\"\"",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-ch-ua-platform-version": "\"10.0.0\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "x-requested-with": "XMLHttpRequest",
        "referrer": "https://gmanga.me/"
    }
    response_text = await fetch(url, headers=headers)
    if response_text:
        manga_data = json.loads(response_text)
        releases = manga_data.get("releases", [])
        teams = manga_data.get("teams", [])
        chapters_info = {}
        for chapter in releases:
            chapter_key = (chapter.get("chapter"), chapter.get("title"))
            team_name = next((m["name"] for m in teams if m["id"] == chapter.get("team_id")), None)
            chapter_id = chapter.get("id")
            if team_name:
                if chapter_key not in chapters_info:
                    chapters_info[chapter_key] = {"chapter": chapter.get("chapter"), "teams": [{"team_name": team_name, "chapter_date": datetime.datetime.fromtimestamp(chapter.get("time_stamp")).strftime('%Y-%m-%d'), "chapter_page": await get_gmanga_chapter_imgs(f"https://gmanga.me/mangas/{id}/{name}/{chapter.get('chapter')}/{chapter_id}")}]}
                else:
                    chapters_info[chapter_key]["teams"].append({"team_name": team_name, "chapter_date": datetime.datetime.fromtimestamp(chapter.get("time_stamp")).strftime('%Y-%m-%d'), "chapter_page": await get_gmanga_chapter_imgs(f"https://gmanga.me/mangas/{id}/{name}/{chapter.get('chapter')}/{chapter_id}")})
            await asyncio.sleep(5)
        return list(chapters_info.values())
    else:
        print("Failed to retrieve data.")
        return None