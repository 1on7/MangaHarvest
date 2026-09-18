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
            if normalized["team_name"] in existing_teams:
                continue
            target["teams"].append(normalized)
            existing_teams.add(normalized["team_name"])

    return sorted(merged.values(), key=lambda item: float(item["chapter"]))


def merge_chapters(existing: list | None, incoming: list | None) -> list:
    """Merge incoming chapters without losing existing team/page data."""
    current = normalize_chapters(existing)
    fresh = normalize_chapters(incoming)

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
            normalize_team_name(team.get("team_name")): team
            for team in target["teams"]
        }

        for team in chapter["teams"]:
            name = normalize_team_name(team.get("team_name")) or "unknown"
            old = by_team.get(name)

            if old is None:
                target["teams"].append(dict(team))
                by_team[name] = target["teams"][-1]
                continue

            if team.get("chapter_date"):
                old["chapter_date"] = team["chapter_date"]
            if team.get("chapter_page"):
                old["chapter_page"] = team["chapter_page"]
            if team.get("source"):
                old["source"] = team["source"]

    return sorted(merged.values(), key=lambda item: float(item["chapter"]))



def find_missing_chapters(chapters: list | None, *, start: int = 1) -> list[int]:
    """Return integer chapter gaps between the lowest and highest chapters.

    Special/decimal chapters are ignored because a gap such as 10.5 is not
    evidence that a numbered chapter is missing.
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
