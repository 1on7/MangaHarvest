import datetime
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

async def fetch(url, method='GET', json=None, headers=None):
    async with aiohttp.ClientSession() as session:
        if method == 'GET':
            async with session.get(url, headers=headers) as response:
                return await response.json()
        elif method == 'POST':
            async with session.post(url, json=json, headers=headers) as response:
                response_txt = await response.json()
                return response_txt
        else:
            raise ValueError(f"Invalid HTTP method: {method}")

async def dilar_info(name):
    url = "https://dilar.tube/api/quick_search"
    headers = {
        "accept": "application/json",
        "accept-language": "en-US,en;q=0.9",
        "content-encoding": "gzip",
        "content-type": "application/json",
        "sec-ch-ua": "\"Chromium\";v=\"122\", \"Not(A:Brand\";v=\"24\", \"Opera\";v=\"108\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin"
    }
    data = {
        "query": name,
        "includes": ["Manga", "Team", "Member"]
    }

    # Send a POST request to the specified URL
    response = await fetch(url, method="POST", json=data, headers=headers)

    # Check if the request was successful
    if response:
        # Extract information for the first manga
        manga_info = response[0]['data']
        if manga_info:
           manga_info = manga_info[0]
           # Extracted manga information
           manga_id = manga_info['id']
           title = manga_info['title']
           summary = manga_info[u'summary']
           try:
               latest_chapter = int(manga_info['latest_chapter'])
           except:
               latest_chapter = float(manga_info['latest_chapter'])
           
           cover_url = f'https://dilar.tube/uploads/manga/cover/{manga_id}/' + manga_info['cover']
        
           return {"title": title, "summary": summary, "cover": cover_url, "id": manga_id, "latest_chapter": latest_chapter}
        else:
          return 'not found'
    else:
        return "Request failed with status code:", 404
      
async def dilar_chapter_imgs(chapter_url):
    headers = {
        "accept-language": "en-US,en;q=0.9",
        "content-encoding": "gzip",
        "content-type": "application/json",
        "sec-ch-ua": "\"Chromium\";v=\"122\", \"Not(A:Brand\";v=\"24\", \"Opera\";v=\"108\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin"
    }

    # Send a POST request to the specified URL
    async with aiohttp.ClientSession() as session:
       async with session.get(chapter_url, headers=headers) as response:
         # Parse the HTML content
         soup = BeautifulSoup(await response.text(), 'html.parser')

         # Find the script tag containing the JSON data
         script_tag = soup.find('script', {'class': 'js-react-on-rails-component'})

         # Extract the JSON data from the script tag
         json_data = json.loads(script_tag.string)

         # Extract pages and storage key from the JSON data
         storage_key = json_data['readerDataAction']['readerData']['release']['storage_key']
         pages = json_data['readerDataAction']['readerData']['release']['pages']
         image_urls = [f"https://dilar.tube/uploads/releases/{storage_key}/hq/" + page for page in pages]
         return image_urls
    

async def dilar_chapters(id, title):
    url = f"https://dilar.tube/api/mangas/{id}/releases"
    headers = {
        "accept": "application/json",
        "accept-language": "en-US,en;q=0.9",
        "content-encoding": "gzip",
        "content-type": "application/json",
        "sec-ch-ua": "\"Chromium\";v=\"122\", \"Not(A:Brand\";v=\"24\", \"Opera\";v=\"108\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin"
    }

    # Send a POST request to the specified URL
    response = await fetch(url, method="GET", headers=headers)
  
  # Check if the request was successful
    if response:
        chapters_info = {}
        for release in response["releases"]:
            # Extract chapter URL
            chapter_url = f"https://dilar.tube/mangas/{id}/{title.replace(' ', '-')}/{release["chapter"]}"
            # Extract chapter number
            chapter_num = release["chapter"]
            chapter_date = datetime.datetime.fromtimestamp(release["time_stamp"]).strftime('%Y-%m-%d')
            chapter_key = (chapter_num, 'Dilar')
            team_name = "Dilar"
            chapters_info[chapter_key] = {"chapter": chapter_num, "teams": [{"team_name": team_name, "chapter_date": chapter_date, "chapter_page": await dilar_chapter_imgs(chapter_url)}]}
        return list(chapters_info.values())
    else:
        return "Request failed with status code:", 404
