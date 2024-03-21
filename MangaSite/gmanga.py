import sys
from os import path
sys.path.append(path.dirname(path.dirname(path.abspath(__file__))))
import asyncio
from aiohttp import ClientSession, ClientTimeout
from bs4 import BeautifulSoup
import re
import json
from utils import date

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
        
async def gmanga_search(name):
    url = 'https://gmanga.site/wp-admin/admin-ajax.php'
    payload = {'title': name, 'action': 'wp-manga-search-manga'}
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
        'referrer': 'https://gmanga.site/'
    }

    response_text = await fetch(url, method='POST', data=payload, headers=headers)
    # Parse the JSON response
    response_data = response_text
    if not response_data["data"]:
        return "not found"
    # Extract title and URL
    manga = response_data.get("data", [])[0]
    title = manga.get("title")
    url = manga.get("url")
    info = await gmanga_info(url)
    return info

async def gmanga_latest_chapters(post_url):
    url = f"{post_url}ajax/chapters/"
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
    response_text = await fetch(url, method='POST', headers=headers)
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

async def gmanga_info(url):
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

    response_text = await fetch(url, method='POST', headers=headers)
    soup = BeautifulSoup(response_text, 'html.parser')
    title = soup.find("div", class_="post-title").find("h1").text.strip()
    description = soup.find("div", class_="summary__content").get_text(strip=True)
    image_url = soup.find("div", class_="summary_image").find("img")["data-src"]
    pattern = r'"manga_id"\s*:\s*"(\d+)"'
    match = re.search(pattern, response_text)
    if match:
        manga_id = match.group(1)
    else:
        print("Manga ID not found.")
        return "not found"
    latest_chapter = await gmanga_latest_chapters(url)
    return {"title": title, "summary": description, "cover": image_url, "id": manga_id, "latest_chapter": latest_chapter, "post_url": url}

async def gmanga_chapter_imgs(chapter_url):
    response_text = await fetch(chapter_url)
    soup = BeautifulSoup(response_text, 'html.parser')
    image_divs = soup.find_all("div", class_="page-break")
    image_urls = [div.find('img')['src'].strip() for div in image_divs]
    return image_urls

async def gmanga_chapters(post_url):
    url = f"{post_url}ajax/chapters/"
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
            chapter_key = (chapter_num, 'gmanga')
            team_name = "gmanga"
            print(chapter_num)
            chapter_number = chapter_num
            chapters_info[chapter_key] = {"chapter": chapter_num, "teams": [{"team_name": team_name, "chapter_date": date.convert_arabic_date_to_numeric(release_date.replace('،', '')), "chapter_page": await gmanga_chapter_imgs(chapter_url)}]}
            await asyncio.sleep(2)
        return list(chapters_info.values())
    else:
        print("Failed to retrieve data.")
        return None
