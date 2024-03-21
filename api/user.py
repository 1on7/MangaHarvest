import base64
import json

import requests

# Open the file in binary mode and read its content
with open("aresnov.txt", "rb") as file:
    file_content = file.read()

# Encode the file content to Base64
encoded_data = base64.b64encode(file_content).decode('utf-8')

# Define the payload with filename and encoded data
payload = {
    "filename": "aresnov.txt",
    "data": encoded_data
}

# Make a POST request to the /upload/ endpoint
response = requests.post("http://127.0.0.1:5000/manga/add", json=payload)

# Print the response
print(response.text)
# Example usage:
data = response.json()
json_data = json.dumps(data, indent=4)
with open("MangaHarvest.json", "w", encoding="utf-8") as f:
    f.write(json_data.encode("utf-8").decode("unicode-escape"))