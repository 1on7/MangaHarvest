import asyncio
import json
from typing import Any, Dict, Optional

import aiohttp

DEFAULT_TIMEOUT = aiohttp.ClientTimeout(total=20, connect=8, sock_read=15)
DEFAULT_HEADERS = {
    "User-Agent": "MangaHarvest/2.0",
    "Accept": "*/*",
}


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
                async with session.request(
                    method,
                    url,
                    data=data,
                    json=json,
                    headers=merged_headers,
                ) as response:
                    response.raise_for_status()
                    return await response.read(), response.content_type, response.charset
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            last_error = exc
            if attempt < retries:
                await asyncio.sleep(1.5 * (attempt + 1))

    raise RuntimeError(f"Request failed after retries: {url}") from last_error


async def fetch_text(url: str, method: str = "GET", *, data: Any = None, headers=None) -> str:
    body, _, charset = await _fetch(url, method, data=data, headers=headers)
    return body.decode(charset or "utf-8", errors="replace")


async def fetch_json(url: str, method: str = "GET", *, data: Any = None, json: Any = None, headers=None):
    body, _, _ = await _fetch(url, method, data=data, json=json, headers=headers)
    return json.loads(body.decode("utf-8"))
