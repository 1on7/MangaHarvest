import sys
from os import path
import time
sys.path.append(path.dirname(path.dirname(path.abspath(__file__))))
from utils import date
import asyncio
from aiohttp import ClientSession, ClientTimeout
from bs4 import BeautifulSoup
import re
import json


chapter_number = 0

async def fetch(url, method='GET', data=None, headers=None):
    async with ClientSession() as session:
        if method == 'GET':
            async with session.get(url, headers=headers) as response:
                return await response.text()
        elif method == 'POST':
            async with session.post(url, data=data, headers=headers) as response:
                return await response.text()
        else:
            raise ValueError(f"Invalid HTTP method: {method}")

async def mangaspark_search(name):
    url = "https://mangaspark.org/wp-admin/admin-ajax.php"
    payload = {
        "action": "wp-manga-search-manga",
        "title": name
    }
    headers = {
        "accept": "application/json, text/javascript, */*; q=0.01",
        "accept-language": "en-US,en;q=0.9",
        "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
        "sec-ch-ua": "\"Not A(Brand\";v=\"99\", \"Opera\";v=\"107\", \"Chromium\";v=\"121\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "x-requested-with": "XMLHttpRequest"
    }
    response_text = await fetch(url, method='POST', data=payload, headers=headers)
    data = json.loads(response_text)
    if not data["data"]:
        return "not found"
    first_item = data["data"][0]
    title = first_item["title"]
    url = first_item["url"]
    info = await mangaspark_info(url)
    return info

async def mangaspark_latest_chapters(id):
    url = "https://mangaspark.org/wp-admin/admin-ajax.php"
    payload = {
        "action": "manga_get_chapters",
        "manga": id
    }
    headers = {
        "accept": "application/json, text/javascript, */*; q=0.01",
        "accept-language": "en-US,en;q=0.9",
        "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
        "sec-ch-ua": "\"Not A(Brand\";v=\"99\", \"Opera\";v=\"107\", \"Chromium\";v=\"121\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "x-requested-with": "XMLHttpRequest",
        "x-oxylabs-render":"html"
    }
    response_text = await fetch(url, method='POST', data=payload, headers=headers)
    if response_text:
        soup = BeautifulSoup(response_text, 'html.parser')
        chapter_items = soup.find('li', class_='wp-manga-chapter')
        try:
            chapter_num = int(chapter_items.a.text.strip())
        except ValueError:
            chapter_num = float(chapter_items.a.text.strip())
        return chapter_num
    else:
        print("Failed to retrieve data.")
        return None

async def mangaspark_info(url):
    headers = {
        "accept": "application/json, text/javascript, */*; q=0.01",
        "accept-language": "en-US,en;q=0.9",
        "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
        "sec-ch-ua": "\"Not A(Brand\";v=\"99\", \"Opera\";v=\"107\", \"Chromium\";v=\"121\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "x-requested-with": "XMLHttpRequest",
        "x-oxylabs-render":"html"
    }
    response_text = await fetch(url, headers=headers)
    soup = BeautifulSoup(response_text, 'html.parser')
    post_title_element = soup.find('div', class_='post-title')
    title = post_title_element.h1.text.strip()
    description_element = soup.find('div', class_='description-summary')
    description = description_element.find('p').text.strip()
    image_url = soup.find('meta', property='og:image')['content']
    pattern = r'"manga_id"\s*:\s*"(\d+)"'
    match = re.search(pattern, response_text)
    if match:
        manga_id = match.group(1)
    else:
        print("Manga ID not found.")
    latest_chapter = await mangaspark_latest_chapters(manga_id)
    return {"title": title, "summary": description, "cover": image_url, "id": manga_id, "latest_chapter": latest_chapter}

async def mangaspark_chapter_imgs(url):
    response_text = await fetch(url)
    soup = BeautifulSoup(response_text, 'html.parser')
    image_divs = soup.find_all('div', class_='page-break no-gaps')
    image_urls = [div.find('img')['src'].strip() for div in image_divs]
    return image_urls

async def mangaspark_chapters(id):
    url = "https://mangaspark.org/wp-admin/admin-ajax.php"
    payload = {
        "action": "manga_get_chapters",
        "manga": id
    }
    headers = {
        "accept": "application/json, text/javascript, */*; q=0.01",
        "accept-language": "en-US,en;q=0.9",
        "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
        "sec-ch-ua": "\"Not A(Brand\";v=\"99\", \"Opera\";v=\"107\", \"Chromium\";v=\"121\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "x-requested-with": "XMLHttpRequest",
        "x-oxylabs-render":"html"
    }
    response_text = await fetch(url, method='POST', data=payload, headers=headers)
    if response_text:
        soup = BeautifulSoup(response_text, 'html.parser')
        chapter_items = soup.find_all('li', class_='wp-manga-chapter')
        chapters_info = {}
        for chapter in chapter_items:
            try:
                chapter_num = int(chapter.a.text.strip())
            except ValueError:
                chapter_num = float(chapter.a.text.strip())
            chapter_url = chapter.a['href']
            release_date = chapter.find('span', class_='chapter-release-date').i.text
            chapter_key = (chapter_num, 'mangaSpark')
            team_name = "MangaSpark"
            print(chapter_num)
            chapter_number = chapter_num
            chapters_info[chapter_key] = {"chapter": chapter_num, "teams": [{"team_name": team_name, "chapter_date": date.convert_arabic_date_to_numeric(release_date.replace('،', '')), "chapter_page": await mangaspark_chapter_imgs(chapter_url)}]}
            await asyncio.sleep(2)
        return list(chapters_info.values())
    else:
        print("Failed to retrieve data.")
        return None
