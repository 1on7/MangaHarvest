import asyncio
import base64
import re
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

import logging

from fastapi.middleware.cors import CORSMiddleware

from bson import ObjectId
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

from MangaSite import asq, aresnov, dilar, gmanga
from config import database
from schema import schemas
from utils import mangaUpdate
from utils.title import title_similarity

@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        await asyncio.to_thread(db.ensure_indexes)
    except Exception:
        logging.getLogger(__name__).warning("MongoDB indexes could not be initialized", exc_info=True)
    yield


app = FastAPI(
    title="MangaHarvest API",
    version="2.1.1",
    description="Asynchronous manga metadata and chapter aggregation API.",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)
db = database

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)


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


def _candidate(result, source: str, query: str):
    if not isinstance(result, dict) or result == NOT_FOUND:
        return None
    title = str(result.get("title") or "")
    similarity = title_similarity(query, title)
    if similarity < 0.35:
        return None
    return (similarity, chapter_number(result.get("latest_chapter")), source, result)


async def _safe_async_call(fn, *args):
    try:
        return await fn(*args)
    except Exception:
        return NOT_FOUND


def _safe_sync_call(fn, *args):
    try:
        return fn(*args)
    except Exception:
        return NOT_FOUND


async def find_best_source(name: str):
    results = await asyncio.gather(
        _safe_async_call(gmanga.gmanga_search, name),
        asyncio.to_thread(_safe_sync_call, aresnov.get_aresnov_info, name),
        _safe_async_call(dilar.dilar_info, name),
        _safe_async_call(asq.asq_info, name),
    )

    candidates = []
    for result, source in zip(results, ("gmanga", "aresnov", "dilar", "asq")):
        candidate = _candidate(result, source, name)
        if candidate:
            candidates.append(candidate)

    return max(candidates, key=lambda item: (item[0], item[1])) if candidates else None


async def fetch_chapters(source: str, info: Dict[str, Any]):
    if source == "gmanga":
        post_url = info.get("post_url")
        if not post_url:
            return []
        chapters = await gmanga.gmanga_chapters(post_url)
        info.pop("post_url", None)
        return chapters or []

    if source == "aresnov":
        title = clean_name(str(info.get("title", ""))).replace(" ", "-")
        return (
            await asyncio.to_thread(aresnov.get_aresnov_chapters, title)
            if title
            else []
        )

    if source == "dilar":
        return await dilar.dilar_chapters(info.get("id"), info.get("title")) or []

    if source == "asq":
        post_url = info.get("post_url")
        if not post_url:
            return []
        chapters = await asq.asq_chapters(post_url)
        info.pop("post_url", None)
        return chapters or []

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
    if len(upload_data.data) > 2_000_000:
        raise HTTPException(status_code=413, detail="Payload is too large")

    try:
        decoded = base64.b64decode(upload_data.data, validate=True).decode("utf-8")
    except (ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid base64 UTF-8 payload") from exc

    names = [clean_name(value) for value in decoded.splitlines()]
    names = [value for value in names if value]
    if len(names) > 100:
        raise HTTPException(status_code=413, detail="Maximum 100 manga names per request")

    results = []
    for name in names:
        selected = await find_best_source(name)
        if selected is None:
            results.append({"name": name, "status": "not_found"})
            continue

        _, _, source, info = selected
        chapters = await fetch_chapters(source, info)

        metadata = await asyncio.to_thread(
            mangaUpdate.get_manga_updates_data,
            info.get("title", name),
        )
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
            manga_id, status = await asyncio.to_thread(
                update_manga_documents,
                title,
                info,
                chapters,
            )
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


@app.get("/api/v1/manga/{manga_id}")
async def info_manga_v1(manga_id: str):
    return await info_manga(manga_id)


@app.get("/manga/")
async def info_manga(manga_id: Optional[str] = Query(None)):
    if not manga_id:
        raise HTTPException(status_code=400, detail="manga_id is required")

    manga = await asyncio.to_thread(
        db.collection_mamga_info.find_one,
        {"_id": object_id(manga_id)},
    )
    if not manga:
        raise HTTPException(status_code=404, detail="Manga not found")

    manga["_id"] = str(manga["_id"])
    return schemas.mangaInfo(manga)


@app.get("/api/v1/manga/{manga_id}/chapters")
async def chapters_manga_v1(manga_id: str):
    return await chapters_manga(manga_id)


@app.get("/manga/chapters/{manga_id}")
async def chapters_manga(manga_id: str):
    manga = await asyncio.to_thread(
        db.collection_mamga_chapters.find_one,
        {"manga_id": manga_id},
    )
    if not manga:
        raise HTTPException(status_code=404, detail="Chapters not found")
    return schemas.mangaChapters(manga)


def _search_manga_documents(name: str, skip: int, limit: int):
    escaped = re.escape(name.strip())
    return list(
        db.collection_mamga_info.find(
            {"title": {"$regex": escaped, "$options": "i"}}
        )
        .sort("title", 1)
        .skip(skip)
        .limit(limit)
    )


@app.get("/api/v1/manga/search")
async def search_manga_v1(
    name: str = Query(..., min_length=1, max_length=100),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=50),
):
    return await search_manga(name=name, page=page, limit=limit)


@app.get("/manga/search")
async def search_manga(
    name: str = Query(..., min_length=1, max_length=100),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=50),
):
    skip = (page - 1) * limit
    manga_list = await asyncio.to_thread(
        _search_manga_documents,
        name,
        skip,
        limit,
    )

    if not manga_list:
        raise HTTPException(status_code=404, detail="Manga not found")

    for manga in manga_list:
        manga["_id"] = str(manga["_id"])

    return {
        "page": page,
        "limit": limit,
        "count": len(manga_list),
        "results": schemas.list_mangaInfo(manga_list),
    }


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

    result = await asyncio.to_thread(
        db.collection_mamga_info.update_one,
        {"_id": object_id(manga_id)},
        {"$set": changes},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Manga not found")
    return {"message": "Manga updated successfully"}


@app.delete("/manga/{manga_id}")
async def delete_manga(manga_id: str):
    oid = object_id(manga_id)
    result = await asyncio.to_thread(
        db.collection_mamga_info.delete_one,
        {"_id": oid},
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Manga not found")

    await asyncio.to_thread(
        db.collection_mamga_chapters.delete_one,
        {"manga_id": manga_id},
    )
    return {"message": "Manga deleted successfully"}


def _latest_manga_documents(skip: int, limit: int):
    return list(
        db.collection_mamga_info.find()
        .sort("_id", -1)
        .skip(skip)
        .limit(limit)
    )


@app.get("/api/v1/manga/latest")
async def latest_manga_v1(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=50),
):
    return await latest_manga(page=page, limit=limit)


@app.get("/manga/latest")
async def latest_manga(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=50),
):
    skip = (page - 1) * limit
    manga_list = await asyncio.to_thread(
        _latest_manga_documents,
        skip,
        limit,
    )

    if not manga_list:
        raise HTTPException(status_code=404, detail="Manga not found")

    for manga in manga_list:
        manga["_id"] = str(manga["_id"])

    return {
        "page": page,
        "limit": limit,
        "count": len(manga_list),
        "results": schemas.list_mangaInfo(manga_list),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=5000)
