import asyncio
import json as json_lib
from typing import Any, Dict, Optional, Awaitable, TypeVar

import aiohttp

DEFAULT_TIMEOUT = aiohttp.ClientTimeout(total=15, connect=5, sock_read=10)
DEFAULT_HEADERS = {
    "User-Agent": "MangaHarvest/2.2 (+https://manga-harvest.vercel.app)",
    "Accept": "*/*",
}
RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}
T = TypeVar("T")


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

    for attempt in range(retries + 1):
        try:
            async with aiohttp.ClientSession(timeout=DEFAULT_TIMEOUT) as session:
                async with session.request(method, url, data=data, json=json, headers=merged_headers) as response:
                    if response.status in RETRYABLE_STATUS and attempt < retries:
                        await response.read()
                        await asyncio.sleep(min(0.75 * (2 ** attempt), 3.0))
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
