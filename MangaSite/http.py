import asyncio
import json as json_lib
import weakref
from typing import Any, Awaitable, Dict, Optional, TypeVar

import aiohttp

DEFAULT_TIMEOUT = aiohttp.ClientTimeout(total=15, connect=5, sock_read=10)
DEFAULT_HEADERS = {
    "User-Agent": "MangaHarvest/2.2 (+https://manga-harvest.vercel.app)",
    "Accept": "*/*",
}
RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}
T = TypeVar("T")

_sessions: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, aiohttp.ClientSession] = weakref.WeakKeyDictionary()


async def _get_session() -> aiohttp.ClientSession:
    loop = asyncio.get_running_loop()
    session = _sessions.get(loop)
    if session is None or session.closed:
        connector = aiohttp.TCPConnector(limit=20, limit_per_host=6, ttl_dns_cache=300)
        session = aiohttp.ClientSession(timeout=DEFAULT_TIMEOUT, connector=connector)
        _sessions[loop] = session
    return session


async def close_sessions():
    sessions = list(_sessions.values())
    _sessions.clear()
    for session in sessions:
        if not session.closed:
            await session.close()


async def _fetch(
    url: str,
    method: str = "GET",
    *,
    data: Any = None,
    json: Any = None,
    headers: Optional[Dict[str, str]] = None,
    retries: int = 2,
):
    merged_headers = {**DEFAULT_HEADERS, **(headers or {})}
    last_error: Optional[Exception] = None
    session = await _get_session()

    for attempt in range(retries + 1):
        try:
            async with session.request(
                method,
                url,
                data=data,
                json=json,
                headers=merged_headers,
            ) as response:
                if response.status in RETRYABLE_STATUS and attempt < retries:
                    await response.read()
                    retry_after = response.headers.get("Retry-After")
                    try:
                        delay = min(float(retry_after), 5.0) if retry_after else 0.75 * (2 ** attempt)
                    except ValueError:
                        delay = 0.75 * (2 ** attempt)
                    await asyncio.sleep(min(delay, 5.0))
                    continue
                response.raise_for_status()
                return await response.read(), response.content_type, response.charset
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            last_error = exc
            if attempt < retries:
                await asyncio.sleep(min(0.75 * (2 ** attempt), 3.0))

    raise RuntimeError(f"Request failed after retries: {url}") from last_error


async def fetch_text(
    url: str,
    method: str = "GET",
    *,
    data: Any = None,
    headers: Optional[Dict[str, str]] = None,
) -> str:
    body, _, charset = await _fetch(url, method, data=data, headers=headers)
    return body.decode(charset or "utf-8", errors="replace")


async def fetch_json(
    url: str,
    method: str = "GET",
    *,
    data: Any = None,
    json: Any = None,
    headers: Optional[Dict[str, str]] = None,
):
    body, _, _ = await _fetch(url, method, data=data, json=json, headers=headers)
    try:
        return json_lib.loads(body.decode("utf-8"))
    except json_lib.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON response: {url}") from exc


async def gather_limited(
    coroutines: list[Awaitable[T]],
    *,
    limit: int = 6,
    return_exceptions: bool = False,
) -> list[T]:
    semaphore = asyncio.Semaphore(max(1, limit))

    async def run(coro):
        async with semaphore:
            return await coro

    return await asyncio.gather(
        *(run(coro) for coro in coroutines),
        return_exceptions=return_exceptions,
    )
