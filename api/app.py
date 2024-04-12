import base64
import sys
from os import path

sys.path.append(path.dirname(path.dirname(path.abspath(__file__))))
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from typing import Optional
from pydantic import BaseModel
from MangaSite import gmanga, aresnov, dilar, asq, teamXnovel
from utils import mangaUpdate
from config import database
from schema import schemas
from bson import ObjectId

app = FastAPI()

db = database


class UploadData(BaseModel):
    data: str  # Assuming the data will be received as a string


# Create (POST) operation to add new manga
@app.post("/manga/add")
async def add_manga(upload_data: UploadData, request: Request):
    data = upload_data.data
    # Decode the Base64-encoded data back to binary
    decoded_data = base64.b64decode(data)
    # Convert binary data to string
    decoded_str = decoded_data.decode('utf-8')
    # Split the string into individual names
    names = decoded_str.split('\n')

    for position, name in enumerate(names):
        print(name)
        manga_found = False
        max_last_chapter = -1
        selected_info = None
        manga_web = ''
        
        # Try getting manga info from gmanga
        info_gmanga = await gmanga.gmanga_search(name)
        if info_gmanga != "not found":
            gmanga_last_chapter = info_gmanga.get('latest_chapter')
            if gmanga_last_chapter > max_last_chapter:
                max_last_chapter = gmanga_last_chapter
                selected_info = info_gmanga
                manga_web = 'gmanga'
                print(manga_web)
                manga_found = True
                
        # Try getting manga info from aresnov
        info_aresnov = aresnov.get_aresnov_info(name)
        if info_aresnov != "not found":
            aresnov_last_chapter = info_aresnov.get('latest_chapter')
            alternative_title = info_aresnov.get('alternative_title')
            if aresnov_last_chapter >= max_last_chapter:
                max_last_chapter = aresnov_last_chapter
                info_aresnov.pop('alternative_title')
                selected_info = info_aresnov
                manga_web = 'aresnov'
                print(manga_web)
                manga_found = True

        # Try getting manga info from mangaSpark
        info_dilar = await dilar.dilar_info(name)
        if info_dilar != "not found":
            dilar_last_chapter = info_dilar.get('latest_chapter')
            if dilar_last_chapter >= max_last_chapter:
                max_last_chapter = dilar_last_chapter
                selected_info = info_dilar
                manga_web = 'dilar'
                print(manga_web)
                manga_found = True
        
        # Try getting manga info from mangaSpark
        info_asq = await asq.asq_info(name)
        if info_asq != "not found":
            asq_last_chapter = info_asq.get('latest_chapter')
            if asq_last_chapter >= max_last_chapter:
                max_last_chapter = asq_last_chapter
                selected_info = info_asq
                manga_web = 'asq'
                print(manga_web)
                manga_found = True
        
        # Try getting manga info from mangaSpark
        info_teamXnovel = await teamXnovel.teamXnovel_info(name)
        if info_teamXnovel != "not found":
             selected_info = info_teamXnovel
             manga_web = 'teamXnovel'
             print(manga_web)
             manga_found = True

        if manga_web == 'gmanga':
            chapters = await gmanga.gmanga_chapters(selected_info.get('post_url'))
            selected_info.pop('post_url')

        if manga_web == 'aresnov':
            title = str(info_aresnov.get('title'))
            chapters = aresnov.get_aresnov_chapters(title.replace(' ', '-'))

        if manga_web == 'dilar':
            chapters = await dilar.dilar_chapters(selected_info.get('id'), selected_info.get('title'))
        
        if manga_web == 'asq':
            chapters = await asq.asq_chapters(selected_info.get('post_url'))
            selected_info.pop('post_url')
            
        if manga_found:
            try:
                type, year, rate, categories, associated_titles, status = mangaUpdate.get_manga_updates_data(
                    selected_info.get('title'))
            except:
                type, year, rate, categories, associated_titles, status = mangaUpdate.get_manga_updates_data(
                    alternative_title)
            selected_info.update({"year": year, "rate": round(rate, 1), "associated": associated_titles,
                                  "categories": categories, "status": status, "type": type})

            # Insert manga info into manga_collection
            manga_insert_result = db.collection_mamga_info.insert_one(selected_info)
            manga_id = str(manga_insert_result.inserted_id)

            # Add manga ID to each chapter document before inserting
            chapters_list = {"manga_id": manga_id, "chapters": chapters}
            db.collection_mamga_chapters.insert_one(chapters_list)

    return JSONResponse(content=None, status_code=200)


# Info (GET) operation to get manga by id
@app.get("/manga/")
async def info_manga(manga_id: Optional[str] = Query(None)):
    manga = db.collection_mamga_info.find_one({"_id": ObjectId(manga_id)})
    # Convert ObjectId to string
    if manga and "_id" in manga:
        manga["_id"] = str(manga["_id"])
        return schemas.mangaInfo(manga)
    else:
        return {"message": "Manga not found"}

@app.get("/manga/chapters/{manga_id}")
async def chapters_manga(manga_id: str):
    manga = db.collection_mamga_chapters.find_one({"manga_id":manga_id})
    # Convert ObjectId to string
    if manga:
        return schemas.mangaChapters(manga)
    else:
        raise HTTPException(status_code=404, detail="Chapters not found")

# search (GET) operation to search manga by name
@app.get("/manga/search")
async def search_manga(name: Optional[str] = Query(None)):
    if name:
        # Search for documents where the title contains the provided query string
        manga_info_list = db.collection_mamga_info.find({"title": {"$regex": name, "$options": "i"}})
        # Convert ObjectId to string and return manga info
        manga_list = []
        for manga in manga_info_list:
            manga["_id"] = str(manga["_id"])
            manga_list.append(manga)
        if manga_list:
            return schemas.list_mangaInfo(manga_list)
        else:
            return JSONResponse(content={"message": "Manga not found"}, status_code=404)
    else:
        return JSONResponse(content={"message": "Please provide a manga name to search for."}, status_code=400)


# Update (PUT) operation to edit manga by ID
@app.put("/manga/{manga_id}")
async def update_manga(manga_id: str, key: str, value: str):
    manga_info = db.collection_mamga_info.find_one_and_update({"_id": ObjectId(manga_id)}, {"$set": {key: value}})
    if str(manga_info["_id"]) == manga_id:
        return {"message": "Manga updated successfully"}
    raise HTTPException(status_code=404, detail="Manga not found")


# Delete (DELETE) operation to delete manga by ID
@app.delete("/manga/{manga_id}")
async def delete_manga(manga_id: str):
    manga_info = db.collection_mamga_info.find_one_and_delete({"_id": ObjectId(manga_id)})
    if manga_info:
        return {"message": "Manga deleted successfully"}
    raise HTTPException(status_code=404, detail="Manga not found")


# latest (GET) operation to get latest manga
@app.get("/manga/latest")
async def latest_manga():
    manga_info_list = db.collection_mamga_info.find()
    print(manga_info_list)
    if manga_info_list:
        return schemas.list_mangaInfo(manga_info_list)
    else:
        return JSONResponse(content={"message": "Manga not found"}, status_code=404)


# Run the FastAPI application with uvicorn
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=5000)
