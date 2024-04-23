import asyncio
import sys
from os import path

from bs4 import BeautifulSoup
sys.path.append(path.dirname(path.dirname(path.abspath(__file__))))

import re
import time
from utils import date, mangaUpdate
import json
import cloudscraper

def get_aresnov_summary(post_url):
    # Create a cloudscraper session
    scraper = cloudscraper.create_scraper(
        browser={
            'browser': 'firefox',
            'platform': 'windows',
            'mobile': False
        }
    )

    # Make a request to the URL
    response = scraper.get(post_url)
    html_content = response.text
    
    # Parse the HTML content
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Find the span element with class="alternative" and extract its text
    alternative_span = soup.find('span', class_='alternative')
    
    # Check if alternative_span is not None before accessing its text
    alternative_title = alternative_span.text.strip() if alternative_span else None

    # Extract information using regex
    release_date_match = re.search(r'تاريخ الإصدار <i>(.*?)</i>', html_content)
    release_date = release_date_match.group(1) if release_date_match else None

    author_match = re.search(r'المؤلف <i>(.*?)</i>', html_content)
    author = author_match.group(1) if author_match else None

    artist_match = re.search(r'الرسام <i>(.*?)</i>', html_content)
    artist = artist_match.group(1) if artist_match else None
    
    description_match = re.search(r'description">.*>(.*?)<\/p>', html_content)
    description = description_match.group(1).strip() if description_match else None

    return release_date, author, artist, description, alternative_title

def get_aresnov_info(name):
    # Create a CloudScraper instance
    scraper = cloudscraper.create_scraper(
        browser={
            'browser': 'firefox',
            'platform': 'windows',
            'mobile': False
        }
    )

    # Define the request payload
    payload = {
        "action": "ts_ac_do_search",
        "ts_ac_query": name
    }

    # Send a POST request to the specified URL
    response = scraper.post(
        "https://scarmanga.com/wp-admin/admin-ajax.php", data=payload)

    # Check if the request was successful
    if response.status_code == 200: 
        # Parse the JSON response
            data = response.json()
            series = data["series"][0]['all']
            print(series)
            if series:  # Check if the list is not empty
                serie = series[0]
                post_image = serie.get("post_image")
                post_title = serie.get("post_title")
                post_link = serie.get("post_link")
                post_latest = serie.get("post_latest")
                post_id = serie.get("ID")
                info = get_aresnov_summary(post_link)
                summary = info[3]
                alternative_title = info[4]

                return {"title": post_title, "summary": summary, "cover": post_image, "id": post_id, "latest_chapter": int(post_latest), "alternative_title": alternative_title}
            else:
                return "not found"
    else:
        return "Request failed with status code:", response.status_code

# Call the function to scrape manhuascarlet.com

def aresnov_chapter_imgs(url):
    # Create a cloudscraper session
    scraper = cloudscraper.create_scraper(
        browser={
            'browser': 'firefox',
            'platform': 'windows',
            'mobile': False
        }
    )

    # Make a request to the URL
    response = scraper.get(url)

    # Check if the request was successful
    if response.status_code == 200:
        html = response.text

        # Regex pattern to match image URLs
        pattern = r'<img decoding="async" src="(.*?)" alt=".*?>'

        # Find all matches of the pattern
        matches = re.findall(pattern, html)

        # Create a list to store image URLs
        images = []

        # Add each image URL to the list
        for match in matches:
            images.append(match)

        return images
    else:
        # If the request was unsuccessful, return None
        print("Error:", response.status_code)
        return None

def get_aresnov_chapters(name):
    # Create a cloudscraper session
    scraper = cloudscraper.create_scraper(
        browser={
            'browser': 'firefox',
            'platform': 'windows',
            'mobile': False
        }
    )

    # Make a request to the URL
    response = scraper.get(f'https://scarmanga.com/series/{name}')

    # Check if the request was successful
    if response.status_code == 200:
        html = response.text
        # Regex pattern to match the chapter number and URL
        pattern = r'<a.href="(.*?)">\s*<span class="chapternum">الفصل (\d+)<\/span>\s*<span class="chapterdate">(.*?)<\/span>\s*<\/a>\s*<\/div>\s*<\/div>\s*<\/li>'
        matches = re.findall(pattern, html)

        chapters_info = {}

        for match in matches:
            # Extract chapter URL
            chapter_url = match[0]
            # Extract chapter number
            chapter_num = match[1]
            chapter_date = date.convert_arabic_date_to_numeric(match[2])
            chapter_key = (chapter_num, 'Aresnov')
            team_name = "Aresnov"
            chapters_info[chapter_key] = {"chapter": chapter_num, "teams": [{"team_name": team_name, "chapter_date": chapter_date, "chapter_page": aresnov_chapter_imgs(chapter_url)}]}
        return list(chapters_info.values())
    else:
        # If the request was unsuccessful, return None
        print("Error:", response.status_code)
        return None
