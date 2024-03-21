import json
import re
import cloudscraper

def get_manga_updates_data(search_query):
    # Create a CloudScraper session
    scraper = cloudscraper.create_scraper(disableCloudflareV1=True,
             browser={
                 'browser': 'chrome',
                 'platform': 'windows',
                 'desktop': True
             }
    )
    # Define the base URL for the MangaUpdates API
    base_url = "https://api.mangaupdates.com/v1/series/search"

    # Define the payload with the search key
    payload = {
        "search": search_query,
        # Add other parameters if needed
        "page": 1
    }

    # Make the POST request to the API
    response = scraper.post(base_url, json=payload)

    # Check if the request was successful (status code 200)
    if response.status_code == 200:
        # Extract and return the response content
        data = response.json()
        series_info = {}
        results = data.get('results', [])
        if results:
            first_result = results[0]
            record = first_result.get('record', {})
            series_info['series_id'] = record.get('series_id')
            series_info['title'] = record.get('title')
            series_info['type'] = record.get('type')
            series_info['year'] = record.get('year')
            series_info['bayesian_rating'] = record.get('bayesian_rating')
            series_info['genres'] = [genre['genre'] for genre in record.get('genres', [])]
            associated, status = get_manga_associated(series_info['series_id'])
            return series_info['type'], series_info['year'], series_info['bayesian_rating'], series_info['genres'], associated, status
        else:
            print("No results found.")
            return None
    else:
        # Return None if the request was unsuccessful
        print("Error:", response.text)
        return None

def get_manga_associated(id):
  # Create a CloudScraper session
    scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True})
    
    # Construct the URL with the series ID
    url = f"https://api.mangaupdates.com/v1/series/{id}"
    
    # Make the GET request to the URL
    response = scraper.get(url)
    associated_titles = {}
    # Check if the request was successful (status code 200)
    if response.status_code == 200:
       data = response.json()
       associated_titles = data["associated"]
       status = data['status']
       status_pattern = r'\d+ .*?\((.*?)\)'
       match = re.search(status_pattern, data['status'])
       if match:
           status = match.group(1)
           return associated_titles, status
       else:
        return associated_titles, ""
    else:
        print("Error:", response.text)
        return None