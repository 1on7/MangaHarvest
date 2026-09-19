from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

_CHAPTER_PATTERNS = (
    re.compile(r"(?i)\\bchapter\\s*[-_:#.]?\\s*(\\d+(?:\\.\\d+)?)"),
    re.compile(r"(?i)\\bch\\.?\\s*[-_:#.]?\\s*(\\d+(?:\\.\\d+)?)"),
)


def absolute_url(base_url: str, value: str | None) -> str:
    value = str(value or "").strip()
    if not value:
        return ""
    return urljoin(base_url, value)


def valid_http_url(value: str | None) -> bool:
    try:
        parsed = urlparse(str(value or "").strip())
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
    except ValueError:
        return False


def unique_urls(values) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        value = str(value or "").strip()
        if value and valid_http_url(value) and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def chapter_number(value, *, href: str | None = None):
    text = str(value or "").strip()

    for pattern in _CHAPTER_PATTERNS:
        match = pattern.search(text)
        if match:
            number = float(match.group(1))
            return int(number) if number.is_integer() else number

    # URLs often contain the chapter number even when the visible label is
    # translated or abbreviated. Prefer an explicit chapter segment.
    if href:
        for pattern in _CHAPTER_PATTERNS:
            match = pattern.search(str(href))
            if match:
                number = float(match.group(1))
                return int(number) if number.is_integer() else number

    match = re.search(r"(?<!\\d)(\\d+(?:\\.\\d+)?)(?!\\d)", text)
    if not match:
        return None

    number = float(match.group(1))
    return int(number) if number.is_integer() else number


def extract_image_urls(soup: BeautifulSoup, *, base_url: str = "") -> list[str]:
    candidates = []
    for image in soup.select("img"):
        for attr in ("data-src", "data-lazy-src", "data-original", "data-url", "src"):
            value = image.get(attr)
            if value:
                candidates.append(value)

        srcset = image.get("data-srcset") or image.get("srcset")
        if srcset:
            for item in srcset.split(","):
                candidates.append(item.strip().split(" ")[0])

    normalized = [absolute_url(base_url, value) if base_url else str(value).strip() for value in candidates]
    return unique_urls(normalized)

from utils.title import title_similarity


def best_match(items, query: str, *, title_keys=("title", "name", "post_title")):
    """Pick the closest search result instead of blindly trusting the first item."""
    scored = []
    for index, item in enumerate(items or []):
        if not isinstance(item, dict):
            continue
        candidate = next((item.get(key) for key in title_keys if item.get(key)), "")
        score = title_similarity(query, str(candidate))
        scored.append((score, -index, item))
    if not scored:
        return None
    return max(scored, key=lambda value: (value[0], value[1]))[2]
