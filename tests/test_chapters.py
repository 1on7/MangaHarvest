from utils.chapters import (
    find_missing_chapters,
    merge_chapters,
    validate_chapter,
)


def test_merge_chapters_preserves_source_metadata():
    result = merge_chapters(
        [{"chapter": 5, "teams": [{"team_name": "Team A", "source": "gmanga", "chapter_page": ["a.jpg"]}]}],
        [{"chapter": 5, "teams": [{"team_name": "Team A", "source": "dilar", "chapter_page": ["b.jpg"]}]}],
    )
    assert result[0]["teams"][0]["source"] == "dilar"
    assert result[0]["teams"][0]["chapter_page"] == ["b.jpg"]


def test_merge_chapters_preserves_existing_and_adds_new_teams():
    result = merge_chapters(
        [{"chapter": 10, "teams": [{"team_name": "Team A", "chapter_date": "old", "chapter_page": ["old.jpg"]}]}],
        [{"chapter": 10, "teams": [
            {"team_name": "Team A", "chapter_date": "new", "chapter_page": []},
            {"team_name": "Team B", "chapter_date": "new", "chapter_page": ["b.jpg"]},
        ]}, {"chapter": 11, "teams": []}],
    )
    assert [item["chapter"] for item in result] == [10, 11]
    assert result[0]["teams"][0]["chapter_date"] == "new"
    assert result[0]["teams"][0]["chapter_page"] == ["old.jpg"]
    assert result[0]["teams"][1]["team_name"] == "Team B"


def test_validate_chapter_detects_missing_pages_and_duplicate_teams():
    valid, errors = validate_chapter({
        "chapter": 10,
        "teams": [
            {"team_name": "Team A", "chapter_page": ["a.jpg"]},
            {"team_name": "Team A", "chapter_page": []},
        ],
    })
    assert not valid
    assert any("duplicate team" in error for error in errors)
    assert any("no pages" in error for error in errors)


def test_validate_chapter_accepts_valid_data():
    valid, errors = validate_chapter({
        "chapter": 10,
        "teams": [{"team_name": "Team A", "chapter_page": ["a.jpg"]}],
    })
    assert valid
    assert errors == []


def test_validate_chapter_allows_chapter_without_team_data():
    valid, errors = validate_chapter({"chapter": 11, "teams": []})
    assert valid
    assert errors == []


def test_find_missing_chapters_ignores_decimal_chapters():
    assert find_missing_chapters([
        {"chapter": 1},
        {"chapter": 2},
        {"chapter": 4},
        {"chapter": 4.5},
    ]) == [3]


def test_find_missing_chapters_returns_empty_for_contiguous_or_too_short_data():
    assert find_missing_chapters([
        {"chapter": 1},
        {"chapter": 2},
        {"chapter": 3},
    ]) == []
    assert find_missing_chapters([{"chapter": 10}]) == []
