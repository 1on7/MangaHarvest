
import os
from pymongo import MongoClient

MONGO_URI = os.getenv("MONGO_URI")

if not MONGO_URI:
    raise RuntimeError("MONGO_URI is not configured")

client = MongoClient(MONGO_URI)

db = client["manga_db"]

info_collection = db["info"]
chapters_collection = db["chapters"]
