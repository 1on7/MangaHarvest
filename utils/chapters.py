from __future__ import annotations

from collections import defaultdict
from typing import Any


def chapter_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if number.is_integer() else number


def normalize_team_name(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


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

        target = merged.setdefault(number, {
            "chapter": number,
            "teams": [],
        })

        teams = item.get("teams") or []
        if isinstance(teams, dict):
            teams = [teams]

        existing_teams = {
            normalize_team_name(team.get("team_name"))
            for team in target["teams"]
            if isinstance(team, dict)
        }

        for team in teams:
            if not isinstance(team, dict):
                continue

            name = normalize_team_name(team.get("team_name")) or "unknown"
            if name in existing_teams:
                continue

            pages = team.get("chapter_page") or []
            if not isinstance(pages, list):
                pages = [pages]

            target["teams"].append({
                "team_name": name,
                "chapter_date": str(team.get("chapter_date") or ""),
                "chapter_page": [str(page).strip() for page in pages if str(page).strip()],
            })
            existing_teams.add(name)

    return sorted(
        merged.values(),
        key=lambda item: float(item["chapter"]),
    )
