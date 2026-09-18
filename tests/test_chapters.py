from utils.chapters import normalize_chapters


def test_normalize_chapters_sorts_and_merges():
    chapters = [
        {
            "chapter": "10",
            "teams": [{"team_name": " Team A ", "chapter_date": "2026-01-10", "chapter_page": [" a.jpg "]}],
        },
        {
            "chapter": 2,
            "teams": [{"team_name": "Team B", "chapter_date": "2026-01-02", "chapter_page": ["b.jpg"]}],
        },
        {
            "chapter": 10.0,
            "teams": [
                {"team_name": "Team A", "chapter_date": "duplicate", "chapter_page": ["duplicate.jpg"]},
                {"team_name": "Team C", "chapter_date": "2026-01-10", "chapter_page": ["c.jpg"]},
            ],
        },
    ]

    result = normalize_chapters(chapters)

    assert [item["chapter"] for item in result] == [2, 10]
    assert [team["team_name"] for team in result[1]["teams"]] == ["Team A", "Team C"]
    assert result[1]["teams"][0]["chapter_page"] == ["a.jpg"]


def test_normalize_chapters_ignores_invalid_entries():
    result = normalize_chapters([
        None,
        {"chapter": "abc", "teams": []},
        {"chapter": 1, "teams": {"team_name": "Team", "chapter_page": "page.jpg"}},
    ])

    assert result == [{
        "chapter": 1,
        "teams": [{
            "team_name": "Team",
            "chapter_date": "",
            "chapter_page": ["page.jpg"],
        }],
    }]


from utils.chapters import merge_chapters


def test_merge_chapters_preserves_existing_and_adds_new_teams():
    result = merge_chapters(
        [{"chapter": 10, "teams": [{"team_name": "Team A", "chapter_date": "old", "chapter_page": ["old.jpg"]}]}],
        [{"chapter": 10, "teams": [{"team_name": "Team A", "chapter_date": "new", "chapter_page": []}, {"team_name": "Team B", "chapter_date": "new", "chapter_page": ["b.jpg"]}]}, {"chapter": 11, "teams": []}],
    )
    assert [item["chapter"] for item in result] == [10, 11]
    assert result[0]["teams"][0]["chapter_date"] == "new"
    assert result[0]["teams"][0]["chapter_page"] == ["old.jpg"]
    assert result[0]["teams"][1]["team_name"] == "Team B"
