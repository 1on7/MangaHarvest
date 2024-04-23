import datetime
import html
import sys
from os import path

from bs4 import BeautifulSoup
sys.path.append(path.dirname(path.dirname(path.abspath(__file__))))

import re
import time
from utils import date
import json

import aiohttp
import asyncio

async def fetch(url, method='GET', data=None, headers=None):
    async with aiohttp.ClientSession() as session:
        if method == 'GET':
            async with session.get(url, headers=headers) as response:
                return await response.text()
        elif method == 'POST':
            async with session.post(url, data=data, headers=headers) as response:
                response_txt = await response.json()
                return response_txt
        else:
            raise ValueError(f"Invalid HTTP method: {method}")
          
async def asq_latest_chapters(post_url):
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
    response_text = await fetch(post_url, method='GET', headers=headers)
    if response_text:
        # Parse the HTML content
        soup = BeautifulSoup(response_text, 'html.parser')
        
        # Extracting src image
        img_src = soup.find('div', class_='summary_image').img['src']
        
        manga_excerpt = html.unescape(soup.find('div', class_='post-content').p.get_text().strip())

        # Find all list items containing chapter information
        chapter_item = soup.find('li', class_='wp-manga-chapter')

        # Extract number for each chapter
        try:
          # Extract only the numeric part of the chapter number
            chapter_num = float(re.search(r'\d+', chapter_item.a.text.strip()).group())
        except ValueError:
            chapter_num = int(re.search(r'\d+', chapter_item.a.text.strip()).group())
        return chapter_num, img_src, manga_excerpt
    else:
        print("Failed to retrieve data.")
        return None

async def asq_info(name):
    url = "https://3asq.org/wp-admin/admin-ajax.php"
    headers = {
        "accept": "application/json, text/javascript, */*; q=0.01",
        "accept-language": "en-US,en;q=0.9",
        "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
        "sec-ch-ua": "\"Chromium\";v=\"122\", \"Not(A:Brand\";v=\"24\", \"Opera\";v=\"108\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "x-requested-with": "XMLHttpRequest"
    }
    data = {
        "action": "wp-manga-search-manga",
        "title": name
    }

    # Send a POST request to the specified URL
    response = await fetch(url, method="POST", data=data, headers=headers)

    # Check if the request was successful
    if response:
        # Extract information for the first manga
        manga_info = response['data']
        if response['success'] == 'true':
           manga_info = manga_info[0]
           # Extracted manga information
           title = manga_info['title']
           post_url = manga_info['url']
           info = await asq_latest_chapters(post_url)
           summary = info[2]
           latest_chapter = info[0]
           cover_url = info[1]
        
           return {"title": title, "summary": summary, "cover": cover_url, "id": 0, "latest_chapter": int(latest_chapter), "post_url": post_url}
        else:
          return 'not found'
    else:
        return "Request failed with status code:", 404


async def asq_chapter_imgs(chapter_url):
    response_text = await fetch(chapter_url)
    soup = BeautifulSoup(response_text, 'html.parser')
    image_divs = soup.find_all("div", class_="page-break")
    image_urls = [div.find('img')['src'].strip() for div in image_divs]
    return image_urls

async def asq_chapters(post_url):
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
    }
    response_text = await fetch(post_url, method='GET', headers=headers)
    if response_text:
        soup = BeautifulSoup(response_text, 'html.parser')
        chapter_items = soup.find_all('li', class_='wp-manga-chapter')
        chapters_info = {}
        for chapter in chapter_items:
            try:
                # Extract only the numeric part of the chapter number
                chapter_num = float(re.search(r'\d+', chapter.a.text.strip()).group())
            except ValueError:
                chapter_num = int(re.search(r'\d+', chapter.a.text.strip()).group())
            chapter_url = chapter.a['href']
            release_date = chapter.find('span', class_='chapter-release-date').i.text
            chapter_key = (chapter_num, 'asq')
            team_name = "asq"
            print(chapter_num)
            chapter_number = chapter_num
            chapters_info[chapter_key] = {"chapter": chapter_num, "teams": [{"team_name": team_name, "chapter_date": date.convert_arabic_date_to_numeric(release_date.replace('،', '')), "chapter_page": await asq_chapter_imgs(chapter_url)}]}
            await asyncio.sleep(2)
        return list(chapters_info.values())
    else:
        print("Failed to retrieve data.")
        return None
