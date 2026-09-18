import os

from pymongo import MongoClient
from pymongo.collection import Collection

MONGO_URI = os.getenv("MONGO_URI")

if not MONGO_URI:
    raise RuntimeError("MONGO_URI is not configured")

client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
db = client["manga_db"]

collection_manga_info: Collection = db["info"]
collection_manga_chapters: Collection = db["chapters"]

# Backward-compatible aliases for the existing API.
collection_mamga_info = collection_manga_info
collection_mamga_chapters = collection_manga_chapters
