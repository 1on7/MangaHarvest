import base64
import re
from typing import Any, Dict, Optional

from bson import ObjectId
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

from MangaSite import asq, aresnov, dilar, gmanga
from config import database
from schema import schemas
from utils import mangaUpdate

app = FastAPI(title="MangaHarvest API", version="2.0.0")
db = database


class UploadData(BaseModel):
    data: str = Field(..., description="Base64-encoded newline-separated manga names")


NOT_FOUND = "not found"


def object_id(value: str) -> ObjectId:
    if not ObjectId.is_valid(value):
        raise HTTPException(status_code=400, detail="Invalid manga id")
    return ObjectId(value)


def chapter_number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return -1


def clean_name(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


async def find_best_source(name: str):
    candidates = []

    info = await gmanga.gmanga_search(name)
    if info != NOT_FOUND:
        candidates.append((chapter_number(info.get("latest_chapter")), "gmanga", info))

    info = aresnov.get_aresnov_info(name)
    if info != NOT_FOUND:
        info.pop("alternative_title", None)
        candidates.append((chapter_number(info.get("latest_chapter")), "aresnov", info))

    info = await dilar.dilar_info(name)
    if info != NOT_FOUND:
        candidates.append((chapter_number(info.get("latest_chapter")), "dilar", info))

    info = await asq.asq_info(name)
    if info != NOT_FOUND:
        candidates.append((chapter_number(info.get("latest_chapter")), "asq", info))

    if not candidates:
        return None

    return max(candidates, key=lambda item: item[0])


async def fetch_chapters(source: str, info: Dict[str, Any]):
    if source == "gmanga":
        post_url = info.get("post_url")
        if not post_url:
            return []
        chapters = await gmanga.gmanga_chapters(post_url)
        info.pop("post_url", None)
        return chapters

    if source == "aresnov":
        title = clean_name(str(info.get("title", ""))).replace(" ", "-")
        return aresnov.get_aresnov_chapters(title) if title else []

    if source == "dilar":
        return await dilar.dilar_chapters(info.get("id"), info.get("title"))

    if source == "asq":
        post_url = info.get("post_url")
        if not post_url:
            return []
        chapters = await asq.asq_chapters(post_url)
        info.pop("post_url", None)
        return chapters

    return []


def update_manga_documents(title: str, info: Dict[str, Any], chapters: list):
    info = dict(info)
    info.pop("post_url", None)

    existing = db.collection_mamga_info.find_one({"title": title}, {"_id": 1})
    if existing:
        manga_id = str(existing["_id"])
        db.collection_mamga_info.update_one(
            {"_id": existing["_id"]},
            {"$set": info},
        )
        db.collection_mamga_chapters.update_one(
            {"manga_id": manga_id},
            {"$set": {"chapters": chapters}},
            upsert=True,
        )
        return manga_id, "updated"

    try:
        inserted = db.collection_mamga_info.insert_one(info)
        manga_id = str(inserted.inserted_id)
    except DuplicateKeyError:
        existing = db.collection_mamga_info.find_one({"title": title}, {"_id": 1})
        if not existing:
            raise
        manga_id = str(existing["_id"])
        db.collection_mamga_info.update_one(
            {"_id": existing["_id"]},
            {"$set": info},
        )

    db.collection_mamga_chapters.update_one(
        {"manga_id": manga_id},
        {"$set": {"chapters": chapters}},
        upsert=True,
    )
    return manga_id, "created"


@app.get("/health")
async def health():
    return {"status": "ok", "service": "MangaHarvest"}


@app.post("/manga/add")
async def add_manga(upload_data: UploadData):
    try:
        decoded = base64.b64decode(upload_data.data, validate=True).decode("utf-8")
    except (ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid base64 UTF-8 payload") from exc

    results = []
    for raw_name in decoded.splitlines():
        name = clean_name(raw_name)
        if not name:
            continue

        selected = await find_best_source(name)
        if selected is None:
            results.append({"name": name, "status": "not_found"})
            continue

        _, source, info = selected
        chapters = await fetch_chapters(source, info) or []

        metadata = mangaUpdate.get_manga_updates_data(info.get("title", name))
        if metadata:
            manga_type, year, rate, categories, associated, status = metadata
        else:
            manga_type, year, rate, categories, associated, status = "", None, None, [], [], ""

        info.update({
            "year": year,
            "rate": round(rate, 1) if isinstance(rate, (int, float)) else rate,
            "associated": associated or [],
            "categories": categories or [],
            "status": status or "",
            "type": manga_type or "",
        })

        title = clean_name(str(info.get("title") or name))
        info["title"] = title

        try:
            manga_id, status = update_manga_documents(title, info, chapters)
        except DuplicateKeyError as exc:
            raise HTTPException(status_code=409, detail="Manga already exists") from exc

        results.append({
            "name": name,
            "status": status,
            "id": manga_id,
            "source": source,
            "chapters": len(chapters),
        })

    return {"results": results}


@app.get("/manga/")
async def info_manga(manga_id: Optional[str] = Query(None)):
    if not manga_id:
        raise HTTPException(status_code=400, detail="manga_id is required")

    manga = db.collection_mamga_info.find_one({"_id": object_id(manga_id)})
    if not manga:
        raise HTTPException(status_code=404, detail="Manga not found")

    manga["_id"] = str(manga["_id"])
    return schemas.mangaInfo(manga)


@app.get("/manga/chapters/{manga_id}")
async def chapters_manga(manga_id: str):
    manga = db.collection_mamga_chapters.find_one({"manga_id": manga_id})
    if not manga:
        raise HTTPException(status_code=404, detail="Chapters not found")
    return schemas.mangaChapters(manga)


@app.get("/manga/search")
async def search_manga(name: str = Query(..., min_length=1)):
    escaped = re.escape(name.strip())
    manga_list = []
    for manga in db.collection_mamga_info.find({"title": {"$regex": escaped, "$options": "i"}}):
        manga["_id"] = str(manga["_id"])
        manga_list.append(manga)

    if not manga_list:
        raise HTTPException(status_code=404, detail="Manga not found")
    return schemas.list_mangaInfo(manga_list)


class MangaUpdate(BaseModel):
    summary: Optional[str] = None
    cover: Optional[str] = None
    year: Optional[int] = None
    rate: Optional[float] = None
    status: Optional[str] = None
    type: Optional[str] = None


@app.put("/manga/{manga_id}")
async def update_manga(manga_id: str, update: MangaUpdate):
    changes = update.model_dump(exclude_none=True)
    if not changes:
        raise HTTPException(status_code=400, detail="No fields to update")

    result = db.collection_mamga_info.update_one(
        {"_id": object_id(manga_id)},
        {"$set": changes},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Manga not found")
    return {"message": "Manga updated successfully"}


@app.delete("/manga/{manga_id}")
async def delete_manga(manga_id: str):
    oid = object_id(manga_id)
    result = db.collection_mamga_info.delete_one({"_id": oid})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Manga not found")

    db.collection_mamga_chapters.delete_one({"manga_id": manga_id})
    return {"message": "Manga deleted successfully"}


@app.get("/manga/latest")
async def latest_manga():
    manga_list = list(db.collection_mamga_info.find())
    if not manga_list:
        raise HTTPException(status_code=404, detail="Manga not found")
    for manga in manga_list:
        manga["_id"] = str(manga["_id"])
    return schemas.list_mangaInfo(manga_list)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=5000)
