import os

from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.collection import Collection

MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    raise RuntimeError("MONGO_URI is not configured")

client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
db = client["manga_db"]

collection_manga_info: Collection = db["info"]
collection_manga_chapters: Collection = db["chapters"]
collection_source_health: Collection = db["source_health"]

# Backward-compatible aliases for the existing API.
collection_mamga_info = collection_manga_info
collection_mamga_chapters = collection_manga_chapters


def ensure_indexes():
    """Create indexes used by reads, updates, and uniqueness checks."""
    collection_manga_info.create_index(
        [("title", ASCENDING)],
        unique=True,
        name="title_unique",
    )
    collection_manga_info.create_index(
        [("latest_chapter", DESCENDING)],
        name="latest_chapter_desc",
    )
    collection_manga_info.create_index(
        [("updated_at", DESCENDING)],
        name="updated_at_desc",
    )
    collection_manga_info.create_index(
        [("last_checked_at", ASCENDING)],
        name="last_checked_at_asc",
    )
    collection_manga_chapters.create_index(
        [("manga_id", ASCENDING)],
        unique=True,
        name="manga_id_unique",
    )
    collection_source_health.create_index(
        [("source", ASCENDING)],
        unique=True,
        name="source_unique",
    )
    collection_source_health.create_index(
        [("last_checked_at", DESCENDING)],
        name="source_last_checked_desc",
    )
    collection_source_health.create_index(
        [("disabled_until", ASCENDING)],
        name="source_disabled_until",
    )
