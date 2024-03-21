
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi

from motor.motor_asyncio import AsyncIOMotorClient

uri = "mongodb+srv://alihussaindev963:n1W7TM0iLY2bAzGf@cluster0.eg0fzso.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"

# Create a new client and connect to the server
client = AsyncIOMotorClient(uri, server_api=ServerApi('1'))

# Send a ping to confirm a successful connection
try:
    client.admin.command('ping')
    print("Pinged your deployment. You successfully connected to MongoDB!")
except Exception as e:
    print(e)