import asyncio
import base64
import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Optional
import time

import logging
import os

logger = logging.getLogger("mangaharvest")

from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from bson import ObjectId
from fastapi import FastAPI, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from MangaSite import asq, aresnov, dilar, gmanga, mangaSpark
from config import database
from schema import schemas
from utils import mangaUpdate
from utils.chapters import chapter_number as normalized_chapter_number, find_chapter_gaps, merge_chapters, normalize_chapters
from utils.cache import TTLCache
from utils.title import normalize_title, title_search_regex, title_similarity

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

@app.middleware("http")
async def rate_limit_middleware(request, call_next):
    if request.url.path == "/health":
        return await call_next(request)

    client_ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "unknown").split(",")[0].strip()
    now = time.monotonic()
    window_start, count = _rate_limit.get(client_ip, (now, 0))
    if now - window_start >= RATE_LIMIT_WINDOW:
        window_start, count = now, 0
    count += 1
    _rate_limit[client_ip] = (window_start, count)

    if count > RATE_LIMIT_REQUESTS:
        return JSONResponse(status_code=429, content={"success": False, "error": {"status": 429, "message": "Rate limit exceeded", "path": request.url.path}}, headers={"Retry-After": str(max(1, int(RATE_LIMIT_WINDOW - (now - window_start))))})

    response = await call_next(request)
    response.headers["X-RateLimit-Limit"] = str(RATE_LIMIT_REQUESTS)
    response.headers["X-RateLimit-Remaining"] = str(max(0, RATE_LIMIT_REQUESTS - count))
    return response


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": {
                "status": exc.status_code,
                "message": str(exc.detail),
                "path": request.url.path,
            },
        },
        headers=exc.headers,
    )


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
SOURCE_CACHE = TTLCache(ttl_seconds=600, max_size=256)
METADATA_CACHE = TTLCache(ttl_seconds=3600, max_size=512)
UPDATE_CONCURRENCY = 4
RATE_LIMIT_WINDOW = 60
RATE_LIMIT_REQUESTS = 120
_rate_limit: dict[str, tuple[float, int]] = {}


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

    query_normalized = normalize_title(query)
    titles = [str(result.get("title") or "")]
    aliases = result.get("alternative_title") or result.get("alternative_titles") or result.get("aliases") or []
    if isinstance(aliases, str):
        aliases = [aliases]
    if isinstance(aliases, (list, tuple, set)):
        titles.extend(str(value) for value in aliases if value)

    scores = [title_similarity(query, candidate) for candidate in titles]
    similarity = max(scores, default=0.0)

    # Exact normalized matches are always trusted. For fuzzy matches, require
    # a meaningful overlap so a generic one-word query cannot select an
    # unrelated series returned by a source's first search result.
    exact_match = any(
        query_normalized and normalize_title(candidate) == query_normalized
        for candidate in titles
    )
    if not exact_match and similarity < 0.45:
        return None

    return (similarity, chapter_number(result.get("latest_chapter")), source, result)


async def _safe_async_call(fn, *args):
    try:
        return await fn(*args)
    except Exception:
        logger.exception("Async source call failed: %s", getattr(fn, "__name__", repr(fn)))
        return NOT_FOUND


def _safe_sync_call(fn, *args):
    try:
        return fn(*args)
    except Exception:
        logger.exception("Sync source call failed: %s", getattr(fn, "__name__", repr(fn)))
        return NOT_FOUND


async def find_source_candidates(name: str, *, include_slow=True):
    calls = [
        _safe_async_call(gmanga.gmanga_search, name),
        _safe_async_call(dilar.dilar_info, name),
        _safe_async_call(asq.asq_info, name),
        _safe_async_call(mangaSpark.mangaspark_search, name),
    ]
    sources = ["gmanga", "dilar", "asq", "mangaspark"]
    if include_slow:
        calls.append(asyncio.to_thread(_safe_sync_call, aresnov.get_aresnov_info, name))
        sources.append("aresnov")

    results = await asyncio.gather(*calls)
    candidates = []
    for result, source in zip(results, sources):
        candidate = _candidate(result, source, name)
        if candidate:
            candidates.append(candidate)
    return sorted(candidates, key=lambda item: (item[0], item[1]), reverse=True)


async def find_best_source(name: str):
    cache_key = clean_name(name).casefold()
    cached = SOURCE_CACHE.get(cache_key)
    if cached is not None:
        return cached

    candidates = await find_source_candidates(name)
    selected = candidates[0] if candidates else None
    if selected is not None:
        SOURCE_CACHE.set(cache_key, selected)
    return selected



def _record_source_health(source: str, *, success: bool, duration_ms: int, chapters: int = 0, error: str | None = None):
    now = datetime.now(timezone.utc)
    try:
        db.collection_source_health.update_one(
            {"source": source},
            {"$set": {"source": source, "last_checked_at": now, "last_success_at": now if success else None, "last_duration_ms": duration_ms, "last_chapter_count": chapters, "last_error": error}, "$inc": {"checks": 1, "successes": 1 if success else 0, "failures": 0 if success else 1, "chapters_seen": chapters}},
            upsert=True,
        )
    except Exception:
        logger.exception("Failed to record source health for %s", source)


async def fetch_verified_chapters(name: str, *, min_chapter: float | None = None):
    """Fetch chapters from every matching source and merge their teams."""
    candidates = await find_source_candidates(name)
    if not candidates:
        return None, [], []

    results = await asyncio.gather(
        *(fetch_chapters(source, dict(info), min_chapter=min_chapter) for _, _, source, info in candidates),
        return_exceptions=True,
    )
    merged = []
    successful_sources = []
    for candidate, result in zip(candidates, results):
        _, _, source, _ = candidate
        if isinstance(result, Exception) or not result:
            await asyncio.to_thread(_record_source_health, source, success=False, duration_ms=0, error=str(result)[:300] if isinstance(result, Exception) else "No chapters returned")
            continue
        tagged = []
        for chapter in result:
            if not isinstance(chapter, dict):
                continue
            chapter_copy = dict(chapter)
            chapter_copy["teams"] = [
                {
                    **team,
                    "source": source,
                    "verification_status": "verified",
                    "last_verified_at": datetime.now(timezone.utc),
                }
                for team in (chapter.get("teams") or [])
                if isinstance(team, dict)
            ]
            tagged.append(chapter_copy)
        merged = merge_chapters(merged, tagged)
        await asyncio.to_thread(_record_source_health, source, success=True, duration_ms=0, chapters=len(tagged))
        successful_sources.append(source)

    return candidates[0], merged, successful_sources


def _existing_manga_state(title: str):
    existing = db.collection_mamga_info.find_one({"title": title}, {"_id": 1, "latest_chapter": 1})
    if not existing:
        return None, None, []

    manga_id = str(existing["_id"])
    chapter_doc = db.collection_mamga_chapters.find_one({"manga_id": manga_id}, {"chapters": 1})
    chapters = normalize_chapters((chapter_doc or {}).get("chapters") or [])
    stored_latest = max((chapter_number(item.get("chapter")) for item in chapters), default=-1)
    return manga_id, max(float(existing.get("latest_chapter") or -1), stored_latest), chapters


async def fetch_chapters(source: str, info: Dict[str, Any], *, min_chapter: float | None = None):
    if source == "gmanga":
        post_url = info.get("post_url")
        if not post_url:
            return []
        chapters = await gmanga.gmanga_chapters(post_url, min_chapter=min_chapter)
        info.pop("post_url", None)
        return chapters or []

    if source == "aresnov":
        title = clean_name(str(info.get("title", ""))).replace(" ", "-")
        return (
            await asyncio.to_thread(aresnov.get_aresnov_chapters, title, min_chapter=min_chapter)
            if title
            else []
        )

    if source == "dilar":
        return await dilar.dilar_chapters(info.get("id"), info.get("title"), min_chapter=min_chapter) or []

    if source == "asq":
        post_url = info.get("post_url")
        if not post_url:
            return []
        chapters = await asq.asq_chapters(post_url, min_chapter=min_chapter)
        info.pop("post_url", None)
        return chapters or []

    if source == "mangaspark":
        manga_id = info.get("id")
        return await mangaSpark.mangaspark_chapters(manga_id, min_chapter=min_chapter) if manga_id else []

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




def _all_manga_documents(limit: int):
    pipeline = [
        {
            "$addFields": {
                "_queue_priority": {
                    "$switch": {
                        "branches": [
                            {"case": {"$eq": ["$last_update_status", "queued"]}, "then": 4},
                            {"case": {"$eq": ["$last_update_status", "error"]}, "then": 3},
                            {"case": {"$eq": ["$last_update_status", "source_not_found"]}, "then": 2},
                            {"case": {"$eq": ["$last_update_status", "no_chapters"]}, "then": 1}
                        ],
                        "default": 0
                    }
                }
            }
        },
        {"$sort": {"_queue_priority": -1, "_id": 1}},
        {"$limit": limit},
        {
            "$project": {
                "_id": 1,
                "title": 1,
                "latest_chapter": 1,
                "last_update_status": 1,
                "unverified_gaps": 1,
                "attempt_count": 1,
            }
        },
    ]
    return list(db.collection_mamga_info.aggregate(pipeline))


async def update_manga_library(limit: int = 25):
    documents = await asyncio.to_thread(_all_manga_documents, limit)
    semaphore = asyncio.Semaphore(UPDATE_CONCURRENCY)

    async def update_one(document):
        async with semaphore:
            return await _update_one_manga(document)

    return await asyncio.gather(*(update_one(document) for document in documents))


async def _update_one_manga(document):
    manga_id = str(document["_id"])
    title = clean_name(str(document.get("title") or ""))
    if not title:
        return {"id": manga_id, "title": title, "status": "invalid_title"}

    now = datetime.now(timezone.utc)

    # Atomically claim the manga so overlapping updater runs cannot process
    # the same record at the same time.
    claimed = await asyncio.to_thread(
        db.collection_mamga_info.find_one_and_update,
        {
            "$or": [
                {"last_update_status": {"$ne": "updating"}},
                {
                    "last_update_status": "updating",
                    "last_attempt_at": {"$lt": now - __import__("datetime").timedelta(minutes=15)}
                }
            ],
            "_id": document["_id"],
        },
        {
            "$set": {
                "last_update_status": "updating",
                "last_attempt_at": now,
            },
            "$inc": {"attempt_count": 1},
        },
        return_document=ReturnDocument.AFTER,
    )
    if not claimed:
        return {"id": manga_id, "title": title, "status": "skipped"}

    try:
        selected = await find_best_source(title)
        if selected is None:
            await asyncio.to_thread(db.collection_mamga_info.update_one, {"_id": document["_id"]}, {"$set": {"last_checked_at": now, "last_update_status": "source_not_found", "last_update_error": "No matching source found"}})
            return {"id": manga_id, "title": title, "status": "source_not_found"}

        _, source_latest, source, info = selected
        stored_latest = chapter_number(document.get("latest_chapter"))

        # If the primary source has no newer chapter, still verify only when
        # the library has known unverified gaps. This lets another source fill
        # a gap without forcing a full refresh for every up-to-date manga.
        existing_doc = await asyncio.to_thread(
            db.collection_mamga_chapters.find_one,
            {"manga_id": manga_id},
            {"chapters": 1},
        )
        existing_chapters = normalize_chapters((existing_doc or {}).get("chapters") or [])
        known_gaps = document.get("unverified_gaps") or []

        if source_latest >= 0 and stored_latest >= source_latest and not known_gaps:
            await asyncio.to_thread(
                db.collection_mamga_info.update_one,
                {"_id": document["_id"]},
                {"$set": {
                    "source": source,
                    "last_checked_at": now,
                    "last_success_at": now,
                    "last_update_status": "up_to_date",
                    "last_update_error": None,
                }},
            )
            return {
                "id": manga_id,
                "title": title,
                "status": "up_to_date",
                "latest_chapter": stored_latest,
                "missing_chapters": [],
                "unverified_gaps": [],
            }

        incremental_from = stored_latest if not known_gaps else None
        verified_selected, incoming_chapters, sources = await fetch_verified_chapters(title, min_chapter=incremental_from)
        if verified_selected:
            _, _, source, _ = verified_selected
        if not incoming_chapters:
            await asyncio.to_thread(db.collection_mamga_info.update_one, {"_id": document["_id"]}, {"$set": {"source": source, "last_checked_at": now, "last_update_status": "no_chapters", "last_update_error": "No chapters returned by matching sources"}})
            return {"id": manga_id, "title": title, "status": "no_chapters"}

        chapters = merge_chapters(existing_chapters, incoming_chapters)
        latest = max(normalized_chapter_number(item.get("chapter")) for item in chapters)
        unverified_gaps = find_chapter_gaps(chapters)

        # Chapters returned by at least one matching source are verified.
        # Existing chapters that remain untouched keep their previous state.
        for chapter in chapters:
            for team in chapter.get("teams", []):
                team.setdefault("verification_status", "verified")

        await asyncio.to_thread(
            db.collection_mamga_chapters.update_one,
            {"manga_id": manga_id},
            {"$set": {"chapters": chapters, "updated_at": now}},
            upsert=True,
        )
        await asyncio.to_thread(
            db.collection_mamga_info.update_one,
            {"_id": document["_id"]},
            {"$set": {"latest_chapter": latest, "updated_at": now, "source": sources, "last_checked_at": now, "last_success_at": now, "last_update_status": "updated", "last_update_error": None, "missing_chapters": [], "unverified_gaps": unverified_gaps}},
        )

        return {
            "id": manga_id,
            "title": title,
            "status": "updated",
            "latest_chapter": latest,
            "chapters": len(chapters),
            "missing_chapters": [],
            "unverified_gaps": unverified_gaps,
        }
    except Exception as exc:
        logger.exception("Automatic update failed for manga=%s", title)
        await asyncio.to_thread(db.collection_mamga_info.update_one, {"_id": document["_id"]}, {"$set": {"last_checked_at": now, "last_update_status": "error", "last_update_error": str(exc)[:500]}})
        return {"id": manga_id, "title": title, "status": "error"}


@app.get("/api/v1/admin/source-health")
async def source_health(authorization: Optional[str] = Header(None)):
    expected_token = os.getenv("ADMIN_UPDATE_TOKEN")
    supplied_token = authorization.removeprefix("Bearer ").strip() if authorization else ""
    if not expected_token or supplied_token != expected_token:
        raise HTTPException(status_code=401, detail="Unauthorized")
    documents = await asyncio.to_thread(lambda: list(db.collection_source_health.find({}, {"_id": 0}).sort("failures", -1)))
    return {"sources": documents}


@app.post("/api/v1/admin/update")
async def admin_update(
    limit: int = Query(25, ge=1, le=100),
    authorization: Optional[str] = Header(None),
):
    expected_token = os.getenv("ADMIN_UPDATE_TOKEN")
    supplied_token = authorization.removeprefix("Bearer ").strip() if authorization else ""
    if not expected_token or supplied_token != expected_token:
        raise HTTPException(status_code=401, detail="Unauthorized")

    results = await update_manga_library(limit)
    return {
        "processed": len(results),
        "updated": sum(item["status"] == "updated" for item in results),
        "up_to_date": sum(item["status"] == "up_to_date" for item in results),
        "errors": sum(item["status"] == "error" for item in results),
        "results": results,
    }

@app.get("/")
async def root():
    return {
        "service": "MangaHarvest",
        "version": app.version,
        "status": "ok",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health")
async def health():
    return {"status": "ok", "service": "MangaHarvest"}


@app.get("/health/db")
async def health_db():
    try:
        await asyncio.to_thread(db.client.admin.command, {"ping": 1})
        return {"status": "ok", "database": "mongodb"}
    except Exception as exc:
        logger.exception("MongoDB health check failed")
        return {
            "status": "error",
            "database": "mongodb",
            "error": type(exc).__name__,
            "message": str(exc)[:300],
        }


def _queue_manga(name: str):
    title = clean_name(name)
    now = datetime.now(timezone.utc)
    result = db.collection_mamga_info.update_one(
        {"title": title},
        {
            "$setOnInsert": {
                "title": title,
                "latest_chapter": -1,
                "created_at": now,
                "updated_at": now,
                "last_update_status": "queued",
                "attempt_count": 0,
            }
        },
        upsert=True,
    )
    document = db.collection_mamga_info.find_one(
        {"title": title},
        {"_id": 1, "title": 1, "last_update_status": 1},
    )
    return str(document["_id"]), "queued" if result.upserted_id else "already_exists"


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
        try:
            manga_id, status = await asyncio.to_thread(_queue_manga, name)
            results.append({
                "name": name,
                "status": status,
                "id": manga_id,
            })
        except DuplicateKeyError:
            results.append({"name": name, "status": "already_exists"})
        except Exception:
            logger.exception("Failed to queue manga=%s", name)
            results.append({"name": name, "status": "error"})

    return {"results": results}


@app.get("/api/v1/manga/search")
async def search_manga_v1(
    name: str = Query(..., min_length=1, max_length=100),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=50),
):
    return await search_manga(name=name, page=page, limit=limit)


@app.get("/api/v1/manga/latest")
async def latest_manga_v1(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=50),
):
    return await latest_manga(page=page, limit=limit)


@app.get("/api/v1/manga/{manga_id}/chapters")
async def chapters_manga_v1(manga_id: str):
    return await chapters_manga(manga_id)


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
    regex = title_search_regex(name)
    query = {"title": {"$regex": regex, "$options": "i"}}
    collection = db.collection_mamga_info
    return (
        list(collection.find(query).sort("title", 1).skip(skip).limit(limit)),
        collection.count_documents(query),
    )


@app.get("/manga/search")
async def search_manga(
    name: str = Query(..., min_length=1, max_length=100),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=50),
):
    skip = (page - 1) * limit
    manga_list, total = await asyncio.to_thread(
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
        "total": total,
        "pages": (total + limit - 1) // limit,
        "has_next": skip + len(manga_list) < total,
        "has_previous": page > 1,
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
