import datetime
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
    async with ClientSession() as session:
        if method == 'GET':
            async with session.get(url, headers=headers) as response:
                return await response.text()
        elif method == 'POST':
            async with session.post(url, data=data, headers=headers) as response:
                response_txt = await response.text()
                return response_txt
        else:
            raise ValueError(f"Invalid HTTP method: {method}")

async def teamXnovel_summary(post_url):
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

  response_text = await fetch(post_url, method='GET', headers=headers)
  # Parse the HTML content
  soup = BeautifulSoup(response_text, 'html.parser')
  pages = []
  summary = soup.find('div', class_='review-content').p.get_text().strip()
  # Find the pagination list
  pagination_list = soup.find('ul', class_='pagination')
  if pagination_list:
    # Initialize an empty set to store unique page numbers
    page_numbers = set()
    # Initialize an empty list to store the links
    page_links = []

    # Find all list items within the pagination list
    for li in pagination_list.find_all('li', class_='page-item'):
        # Find the anchor tag within the list item
        link = li.find('a')
        if link:
            # Extract the href attribute value (link URL)
          href = link['href']
          # Extract the page number from the href attribute
          page_number = int(href.split('=')[-1])
        # Check if the page number is not already encountered
          if page_number not in page_numbers:
              # Add the page number to the set of unique page numbers
              page_numbers.add(page_number)
              # Append the link URL and page number as a tuple to the list
              page_links.append((page_number, href))

    # Sort the list of links by page number
    page_links.sort(key=lambda x: x[0])

    # Extract only the link URLs from the sorted list
    sorted_page_links = [link[1] for link in page_links]
  else:
    sorted_page_links = post_url
  return summary, sorted_page_links

async def teamXnovel_info(name):
  url = f'https://teamxnovel.com/ajax/search?keyword={name}'
  
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

  response_text = await fetch(url, method='GET', headers=headers)
  # Parse the HTML content
  soup = BeautifulSoup(response_text, 'html.parser')
  first_item = soup.find('ol', class_='list-group').find('li')
  title = first_item.find_all('a')[1].text
  post_url = first_item.find('div', class_='image-parent').a['href']
  img_url = first_item.find('img')['src'].strip()
  info = await teamXnovel_summary(post_url)
  description = info[0]
  latest_chapter = first_item.find('span', class_='badge').text.strip()
  pages = []
  pages.append(post_url + '?page=1')
  for page in info[1]:
    pages.append(page)
  if latest_chapter.isdigit():
    latest_chapter = int(latest_chapter)
  elif latest_chapter:
    latest_chapter = float(latest_chapter)
  return {"title": title, "summary": description, "cover": img_url, "id": 0, "latest_chapter": latest_chapter, 'page_items': pages}

async def teamXnovel_chapter_imgs(chapter_url):
  response_text = await fetch(chapter_url)
  soup = BeautifulSoup(response_text, 'html.parser')
  image_divs = soup.find_all("div", class_="page-break")
  image_urls = [div.find('img')['src'].strip() for div in image_divs]
  return image_urls

async def teamXnovel_chapters(pages):
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
  chapters_info = {}
  for page in pages:
    response_text = await fetch(page, method='GET', headers=headers)
    if response_text:
          soup = BeautifulSoup(response_text, 'html.parser')
          # Find all list items containing chapter information
          chapter_items = soup.find_all('ul')[4]
          chapter_items = chapter_items.find_all('li')
          for chapter in chapter_items:
              ch_num = chapter.find_all('div', class_='epl-num')[1].getText().strip()
              if ch_num != '':
                try:
                    # Extract only the numeric part of the chapter number
                    chapter_num = float(re.search(r'(\d+.\d+)', ch_num).group())
                except:
                    chapter_num = int(re.search(r'(\d+)', ch_num).group())
              
              chapter_url = chapter.a['href']
              release_date = datetime.datetime.strptime(chapter.find('div', class_='epl-date eph-date d-none d-sm-block date-time').getText().strip(), '%Y-%m-%d %H:%M:%S').strftime('%Y-%m-%d')
              chapter_key = (chapter_num, 'asq')
              team_name = "asq"
              print(chapter_num)
              chapter_number = chapter_num
              chapters_info[chapter_key] = {"chapter": chapter_num, "teams": [{"team_name": team_name, "chapter_date": release_date, "chapter_page": await teamXnovel_chapter_imgs(chapter_url)}]}
              await asyncio.sleep(2)
    else:
        print("Failed to retrieve data.")
        return None
  return list(chapters_info.values())
