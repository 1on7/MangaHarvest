import asyncio
import base64
import re
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
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

from MangaSite import asq, aresnov, dilar, gmanga, mangaSpark, mangadex
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

    scored_titles = [
        (title_similarity(query, candidate), normalize_title(candidate) == query_normalized)
        for candidate in titles if candidate
    ]
    similarity = max((score for score, _ in scored_titles), default=0.0)
    exact_match = any(exact for _, exact in scored_titles)
    if not exact_match and similarity < 0.45:
        return None

    latest = chapter_number(result.get("latest_chapter"))
    metadata_bonus = sum(0.01 for key in ("cover", "summary", "post_url", "id") if result.get(key))
    ranking_score = (
        2.0 if exact_match else 0.0,
        round(similarity + min(metadata_bonus, 0.03), 6),
        latest,
    )
    return (ranking_score, latest, source, result)


async def _timed_async_call(source: str, fn, *args, timeout: float = 20.0):
    started = time.monotonic()
    try:
        result = await asyncio.wait_for(fn(*args), timeout=timeout)
        await asyncio.to_thread(_record_source_health, source, success=isinstance(result, dict) and result != NOT_FOUND, duration_ms=int((time.monotonic() - started) * 1000), error=None if isinstance(result, dict) and result != NOT_FOUND else "No metadata returned")
        return result
    except Exception as exc:
        await asyncio.to_thread(_record_source_health, source, success=False, duration_ms=int((time.monotonic() - started) * 1000), error=str(exc)[:300])
        logger.exception("Async source call failed: %s", source)
        return NOT_FOUND


def _safe_sync_call(fn, *args):
    try:
        return fn(*args)
    except Exception:
        logger.exception("Sync source call failed: %s", getattr(fn, "__name__", repr(fn)))
        return NOT_FOUND


async def find_source_candidates(name: str, *, include_slow=True):
    source_calls = [
        ("mangadex", _timed_async_call("mangadex", mangadex.mangadex_search, name)),
        ("gmanga", _timed_async_call("gmanga", gmanga.gmanga_search, name)),
        ("dilar", _timed_async_call("dilar", dilar.dilar_info, name)),
        ("asq", _timed_async_call("asq", asq.asq_info, name)),
        ("mangaspark", _timed_async_call("mangaspark", mangaSpark.mangaspark_search, name)),
    ]

    if include_slow:
        async def timed_aresnov():
            started = time.monotonic()
            try:
                result = await asyncio.wait_for(
                    asyncio.to_thread(aresnov.get_aresnov_info, name),
                    timeout=20.0,
                )
                await asyncio.to_thread(
                    _record_source_health,
                    "aresnov",
                    success=isinstance(result, dict) and result != NOT_FOUND,
                    duration_ms=int((time.monotonic() - started) * 1000),
                    error=None if isinstance(result, dict) and result != NOT_FOUND else "No metadata returned",
                )
                return result
            except asyncio.TimeoutError:
                duration_ms = int((time.monotonic() - started) * 1000)
                await asyncio.to_thread(
                    _record_source_health,
                    "aresnov",
                    success=False,
                    duration_ms=duration_ms,
                    error="Timeout after 20s",
                )
                logger.warning("Source timed out: aresnov")
                return NOT_FOUND
            except Exception as exc:
                await asyncio.to_thread(
                    _record_source_health,
                    "aresnov",
                    success=False,
                    duration_ms=int((time.monotonic() - started) * 1000),
                    error=str(exc)[:300],
                )
                logger.exception("Sync source call failed: aresnov")
                return NOT_FOUND

        source_calls.append(("aresnov", timed_aresnov()))

    async def run_source(source: str, call):
        try:
            result = await asyncio.wait_for(call, timeout=20.0)
        except asyncio.TimeoutError:
            logger.warning("Discovery timeout: %s", source)
            return source, NOT_FOUND
        except Exception:
            logger.exception("Discovery failed: %s", source)
            return source, NOT_FOUND

        await asyncio.to_thread(
            db.collection_mamga_info.update_one,
            {"title": clean_name(name)},
            {"$set": {
                "current_source": source,
                "sources_checked": 0,
                "sources_total": len(source_calls),
            }},
        )
        return source, result

    tasks = [asyncio.create_task(run_source(source, call)) for source, call in source_calls]
    results = []
    for task in asyncio.as_completed(tasks):
        source, result = await task
        results.append((result, source))
        try:
            await asyncio.to_thread(
                db.collection_mamga_info.update_one,
                {"title": clean_name(name)},
                {"$set": {
                    "current_source": source,
                    "sources_checked": len(results),
                    "sources_total": len(source_calls),
                }},
            )
        except Exception:
            logger.exception("Failed to update discovery progress for %s", source)

    candidates = []
    for result, source in results:
        candidate = _candidate(result, source, name)
        if candidate:
            candidates.append(candidate)

    health_docs = await asyncio.to_thread(
        lambda: list(db.collection_source_health.find(
            {"source": {"$in": [source for source, _ in source_calls]}},
            {"_id": 0, "source": 1, "checks": 1, "successes": 1, "last_duration_ms": 1},
        ))
    )
    health = {item["source"]: item for item in health_docs}

    # Skip sources that have been temporarily disabled after repeated failures.
    now = datetime.now(timezone.utc)
    disabled = {
        source
        for source, item in health.items()
        if item.get("disabled_until") and item["disabled_until"] > now
    }
    candidates = [candidate for candidate in candidates if candidate[2] not in disabled]

    def health_score(source: str) -> float:
        item = health.get(source, {})
        checks = max(int(item.get("checks", 0)), 0)
        successes = min(int(item.get("successes", 0)), checks)
        reliability = successes / checks if checks else 0.5
        latency = max(int(item.get("last_duration_ms", 0)), 0)
        latency_score = 1.0 / (1.0 + latency / 1000.0) if latency else 0.5
        return reliability * 0.8 + latency_score * 0.2

    return sorted(
        candidates,
        key=lambda item: (item[0], health_score(item[2]), item[1]),
        reverse=True,
    )

def _merge_source_metadata(candidates):
    if not candidates:
        return None

    _, _, primary_source, primary = candidates[0]
    merged = dict(primary)
    merged["source"] = primary_source
    latest_values = [
        chapter_number(info.get("latest_chapter"))
        for _, _, _, info in candidates
        if isinstance(info, dict) and info.get("latest_chapter") is not None
    ]
    if latest_values:
        merged["latest_chapter"] = max(latest_values)

    for _, _, source, info in candidates[1:]:
        if not isinstance(info, dict):
            continue
        for key, value in info.items():
            if key in {"id", "post_url"} or value in (None, "", [], {}):
                continue
            current = merged.get(key)
            if current in (None, "", [], {}):
                merged[key] = value

        for key in ("alternative_title", "alternative_titles", "aliases", "genres"):
            incoming = info.get(key)
            if not incoming:
                continue
            values = [incoming] if isinstance(incoming, str) else list(incoming) if isinstance(incoming, (list, tuple, set)) else []
            existing = merged.get(key)
            existing_values = [existing] if isinstance(existing, str) else list(existing) if isinstance(existing, (list, tuple, set)) else []
            combined = []
            for value in existing_values + values:
                value = str(value).strip()
                if value and value.casefold() not in {item.casefold() for item in combined}:
                    combined.append(value)
            if combined:
                merged[key] = combined if not isinstance(incoming, str) else ", ".join(combined)

    return merged


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
        update = {
            "$set": {
                "source": source,
                "last_checked_at": now,
                "last_duration_ms": duration_ms,
                "last_chapter_count": chapters,
                "last_error": error,
            },
            "$inc": {
                "checks": 1,
                "successes": 1 if success else 0,
                "failures": 0 if success else 1,
                "chapters_seen": chapters,
            },
        }
        if success:
            update["$set"]["last_success_at"] = now
            update["$set"]["disabled_until"] = None
        else:
            # Temporarily disable repeatedly failing sources. A successful
            # check automatically re-enables the source.
            existing = db.collection_source_health.find_one(
                {"source": source},
                {"failures": 1},
            ) or {}
            failures = int(existing.get("failures", 0))
            if failures + 1 >= 3:
                update["$set"]["disabled_until"] = now + timedelta(hours=6)
        db.collection_source_health.update_one({"source": source}, update, upsert=True)
    except Exception:
        logger.exception("Failed to record source health for %s", source)


async def fetch_verified_chapters(name: str, *, min_chapter: float | None = None, manga_id: str | None = None):
    """Fetch and merge chapters from every matching source with measured health."""
    candidates = await find_source_candidates(name)
    if not candidates:
        return None, [], []

    async def timed_chapters(source: str, info: dict):
        started = time.monotonic()
        try:
            result = await asyncio.wait_for(
                fetch_chapters(source, info, min_chapter=min_chapter),
                timeout=90.0,
            )
            return result, int((time.monotonic() - started) * 1000), None
        except asyncio.TimeoutError:
            return None, int((time.monotonic() - started) * 1000), TimeoutError("Timeout after 90s")
        except Exception as exc:
            return None, int((time.monotonic() - started) * 1000), exc

    results = await asyncio.gather(
        *(timed_chapters(source, dict(info)) for _, _, source, info in candidates)
    )
    merged = []
    successful_sources = []

    for index, (candidate, (result, duration_ms, error)) in enumerate(zip(candidates, results), start=1):
        _, _, source, _ = candidate
        if manga_id:
            try:
                await asyncio.to_thread(
                    db.collection_mamga_info.update_one,
                    {"_id": __import__("bson").ObjectId(manga_id)},
                    {"$set": {"current_source": source, "sources_checked": index}},
                )
            except Exception:
                logger.exception("Failed to update chapter source progress for %s", manga_id)
        if error is not None or not result:
            await asyncio.to_thread(
                _record_source_health,
                source,
                success=False,
                duration_ms=duration_ms,
                error=str(error)[:300] if error else "No chapters returned",
            )
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
        await asyncio.to_thread(
            _record_source_health,
            source,
            success=True,
            duration_ms=duration_ms,
            chapters=len(tagged),
        )
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
    if source == "mangadex":
        return await mangadex.mangadex_chapters(info.get("mangadex_id") or info.get("id"), min_chapter=min_chapter)

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
                    "last_attempt_at": {"$lt": now - timedelta(minutes=15)}
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
        await asyncio.to_thread(
            db.collection_mamga_info.update_one,
            {"_id": document["_id"]},
            {"$set": {
                "last_update_status": "updating",
                "current_source": "discovering",
                "update_started_at": now,
                "sources_checked": 0,
                "sources_total": 0,
            }},
        )
        candidates = await find_source_candidates(title)
        await asyncio.to_thread(
            db.collection_mamga_info.update_one,
            {"_id": document["_id"]},
            {"$set": {
                "current_source": "fetching_chapters",
                "sources_checked": 0,
                "sources_total": len(candidates),
            }},
        )
        selected = candidates[0] if candidates else None
        if selected is None:
            await asyncio.to_thread(db.collection_mamga_info.update_one, {"_id": document["_id"]}, {"$set": {"last_checked_at": now, "last_update_status": "source_not_found", "last_update_error": "No matching source found"}})
            return {"id": manga_id, "title": title, "status": "source_not_found"}

        _, source_latest, source, info = selected
        merged_info = _merge_source_metadata(candidates)
        if merged_info:
            info = merged_info
            source_latest = chapter_number(info.get("latest_chapter"))
            source = info.get("source") or source
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
        stored_gaps = {
            int(value)
            for value in (document.get("unverified_gaps") or [])
            if isinstance(value, (int, float)) and float(value).is_integer()
        }
        detected_gaps = set(find_chapter_gaps(existing_chapters))
        known_gaps = sorted(stored_gaps | detected_gaps)

        # A source can report the current latest chapter while another source
        # has failed to provide a chapter in the middle. Never short-circuit
        # an update when the library contains an unverified gap.
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

        # When gaps exist, request the full chapter range from every matching
        # source so another source can recover the missing chapter(s).
        incremental_from = stored_latest if not known_gaps else None
        verified_selected, incoming_chapters, sources = await fetch_verified_chapters(title, min_chapter=incremental_from, manga_id=str(document["_id"]))
        await asyncio.to_thread(
            db.collection_mamga_info.update_one,
            {"_id": document["_id"]},
            {"$set": {
                "current_source": "merging",
                "sources_checked": len(sources),
            }},
        )
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
    now = datetime.now(timezone.utc)
    for document in documents:
        disabled_until = document.get("disabled_until")
        document["enabled"] = not disabled_until or disabled_until <= now
        document["status"] = "disabled" if not document["enabled"] else (
            "healthy" if document.get("successes", 0) else "unverified"
        )
        if disabled_until and disabled_until <= now:
            document["disabled_until"] = None
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

            # Start an immediate best-effort background update. The scheduled
            # updater remains the durable fallback for serverless instances.
            if status == "queued":
                document = await asyncio.to_thread(
                    db.collection_mamga_info.find_one,
                    {"_id": ObjectId(manga_id)},
                )
                if document:
                    asyncio.create_task(_update_one_manga(document))
                    status = "scraping"

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


@app.get("/api/v1/manga/{manga_id}/status")
async def manga_status(manga_id: str):
    manga = await asyncio.to_thread(
        db.collection_mamga_info.find_one,
        {"_id": object_id(manga_id)},
        {
            "title": 1,
            "latest_chapter": 1,
            "last_update_status": 1,
            "last_checked_at": 1,
            "last_attempt_at": 1,
            "update_started_at": 1,
            "current_source": 1,
            "sources_checked": 1,
            "sources_total": 1,
            "last_success_at": 1,
            "last_update_error": 1,
            "unverified_gaps": 1,
            "attempt_count": 1,
        },
    )
    if not manga:
        raise HTTPException(status_code=404, detail="Manga not found")

    return {
        "id": manga_id,
        "title": manga.get("title"),
        "status": manga.get("last_update_status"),
        "latest_chapter": manga.get("latest_chapter", -1),
        "unverified_gaps": manga.get("unverified_gaps") or [],
        "attempt_count": manga.get("attempt_count", 0),
        "last_checked_at": manga.get("last_checked_at"),
        "last_attempt_at": manga.get("last_attempt_at"),
        "update_started_at": manga.get("update_started_at"),
        "current_source": manga.get("current_source"),
        "sources_checked": manga.get("sources_checked", 0),
        "sources_total": manga.get("sources_total", 0),
        "last_success_at": manga.get("last_success_at"),
        "error": manga.get("last_update_error"),
    }


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
