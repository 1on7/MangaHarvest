[object Object]

def test_merge_chapters_preserves_source_metadata():
    from utils.chapters import merge_chapters
    result = merge_chapters(
        [{"chapter": 5, "teams": [{"team_name": "Team A", "source": "gmanga", "chapter_page": ["a.jpg"]}]}],
        [{"chapter": 5, "teams": [{"team_name": "Team A", "source": "dilar", "chapter_page": ["b.jpg"]}]}],
    )
    assert result[0]["teams"][0]["source"] == "dilar"
    assert result[0]["teams"][0]["chapter_page"] == ["b.jpg"]


def test_validate_chapter_detects_missing_pages_and_duplicate_teams():
    from utils.chapters import validate_chapter
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
    from utils.chapters import validate_chapter
    valid, errors = validate_chapter({
        "chapter": 10,
        "teams": [{"team_name": "Team A", "chapter_page": ["a.jpg"]}],
    })
    assert valid
    assert errors == []
