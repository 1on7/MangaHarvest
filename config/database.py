from pymongo import MongoClient
import sys
from os import path
import ssl

sys.path.append(path.dirname(path.dirname(path.abspath(__file__))))
import base64
from schema import schemas
from bson import ObjectId
import asyncio

client = MongoClient("mongodb+srv://alihussaindev963:n1W7TM0iLY2bAzGf@cluster0.eg0fzso.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")

db = client.manga_db

collection_mamga_info = db["info"]

collection_mamga_chapters = db["chapters"]
