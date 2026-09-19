from __future__ import annotations

from typing import Any


def chapter_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if number.is_integer() else number


def normalize_team_name(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _normalize_team(team: dict) -> dict:
    pages = team.get("chapter_page") or []
    if not isinstance(pages, list):
        pages = [pages]

    normalized = {
        "team_name": normalize_team_name(team.get("team_name")) or "unknown",
        "chapter_date": str(team.get("chapter_date") or ""),
        "chapter_page": [str(page).strip() for page in pages if str(page).strip()],
    }
    if team.get("source"):
        normalized["source"] = str(team["source"])
    if team.get("verification_status"):
        normalized["verification_status"] = str(team["verification_status"])
    if team.get("last_verified_at"):
        normalized["last_verified_at"] = team["last_verified_at"]
    return normalized


def normalize_chapters(chapters: list | None) -> list:
    """Normalize, merge duplicate chapter numbers, and sort chapters numerically."""
    if not chapters:
        return []

    merged: dict[float, dict] = {}

    for item in chapters:
        if not isinstance(item, dict):
            continue

        number = chapter_number(item.get("chapter"))
        if number is None:
            continue

        target = merged.setdefault(number, {"chapter": number, "teams": []})
        existing_teams = {
            normalize_team_name(team.get("team_name"))
            for team in target["teams"]
            if isinstance(team, dict)
        }

        teams = item.get("teams") or []
        if isinstance(teams, dict):
            teams = [teams]

        for team in teams:
            if not isinstance(team, dict):
                continue
            normalized = _normalize_team(team)
            team_key = normalized["team_name"].casefold()
            existing_keys = {name.casefold() for name in existing_teams}
            if team_key in existing_keys:
                continue
            target["teams"].append(normalized)
            existing_teams.add(normalized["team_name"])

    return sorted(merged.values(), key=lambda item: float(item["chapter"]))


def merge_chapters(existing: list | None, incoming: list | None) -> list:
    """Merge incoming chapters without replacing valid data with invalid data."""
    current = normalize_chapters(existing)
    fresh = []
    for chapter in normalize_chapters(incoming):
        valid, _ = validate_chapter(chapter)
        if valid:
            fresh.append(chapter)

    merged: dict[float, dict] = {
        item["chapter"]: {
            "chapter": item["chapter"],
            "teams": [dict(team) for team in item["teams"]],
        }
        for item in current
    }

    for chapter in fresh:
        target = merged.setdefault(
            chapter["chapter"],
            {"chapter": chapter["chapter"], "teams": []},
        )

        by_team = {
            normalize_team_name(team.get("team_name")).casefold(): team
            for team in target["teams"]
        }

        for team in chapter["teams"]:
            name = normalize_team_name(team.get("team_name")) or "unknown"
            old = by_team.get(name.casefold())

            if old is None:
                target["teams"].append(dict(team))
                by_team[name.casefold()] = target["teams"][-1]
                continue

            if team.get("chapter_date"):
                old["chapter_date"] = team["chapter_date"]

            # Keep every valid page URL discovered across sources instead of
            # replacing an existing team's pages with the latest response.
            pages = old.get("chapter_page") or []
            incoming_pages = team.get("chapter_page") or []
            if not isinstance(pages, list):
                pages = [pages]
            if not isinstance(incoming_pages, list):
                incoming_pages = [incoming_pages]
            seen_pages = {str(page).strip() for page in pages if str(page).strip()}
            for page in incoming_pages:
                page = str(page).strip()
                if page and page not in seen_pages:
                    pages.append(page)
                    seen_pages.add(page)
            old["chapter_page"] = pages

            if team.get("source"):
                sources = [value.strip() for value in str(old.get("source") or "").split(",") if value.strip()]
                incoming_source = str(team["source"]).strip()
                if incoming_source and incoming_source not in sources:
                    sources.append(incoming_source)
                old["source"] = ", ".join(sources)

            if team.get("verification_status"):
                old["verification_status"] = team["verification_status"]
            if team.get("last_verified_at"):
                old["last_verified_at"] = team["last_verified_at"]

    return sorted(merged.values(), key=lambda item: float(item["chapter"]))



def find_chapter_gaps(chapters: list | None, *, start: int = 1) -> list[int]:
    """Return integer chapter gaps without claiming they are truly missing.

    A gap can be intentional or can exist on a source that has incomplete
    chapter data, so callers should treat these as unverified gaps.
    Special/decimal chapters are ignored.
    """
    normalized = normalize_chapters(chapters)
    numbers = {
        int(item["chapter"])
        for item in normalized
        if isinstance(item.get("chapter"), int) and item["chapter"] >= start
    }
    if len(numbers) < 2:
        return []

    highest = max(numbers)
    return [number for number in range(start, highest + 1) if number not in numbers]


def find_missing_chapters(chapters: list | None, *, start: int = 1) -> list[int]:
    """Backward-compatible alias for chapter gap detection."""
    return find_chapter_gaps(chapters, start=start)


def validate_chapter(chapter: dict) -> tuple[bool, list[str]]:
    """Validate basic chapter/team integrity before persistence."""
    errors: list[str] = []
    if not isinstance(chapter, dict):
        return False, ["chapter must be an object"]

    if chapter_number(chapter.get("chapter")) is None:
        errors.append("invalid chapter number")

    teams = chapter.get("teams") or []
    if isinstance(teams, dict):
        teams = [teams]
    if not isinstance(teams, list):
        errors.append("teams must be a list")
        return not errors, errors

    # A chapter may temporarily have no teams when a source exposes chapter
    # numbers separately from page data. Keep it for later enrichment.
    if not teams:
        return True, []

    seen: set[str] = set()
    for team in teams:
        if not isinstance(team, dict):
            errors.append("team must be an object")
            continue
        name = normalize_team_name(team.get("team_name"))
        if not name:
            errors.append("team name is empty")
            continue
        key = name.casefold()
        if key in seen:
            errors.append(f"duplicate team: {name}")
        seen.add(key)

        pages = team.get("chapter_page") or []
        if not isinstance(pages, list):
            errors.append(f"pages must be a list for team: {name}")
            continue
        if not pages:
            errors.append(f"no pages for team: {name}")
        elif any(not str(page).strip() for page in pages):
            errors.append(f"empty page URL for team: {name}")

    return not errors, errors
