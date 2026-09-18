[object Object]

def test_merge_chapters_preserves_source_metadata():
    from utils.chapters import merge_chapters
    result = merge_chapters(
        [{"chapter": 5, "teams": [{"team_name": "Team A", "source": "gmanga", "chapter_page": ["a.jpg"]}]}],
        [{"chapter": 5, "teams": [{"team_name": "Team A", "source": "dilar", "chapter_page": ["b.jpg"]}]}],
    )
    assert result[0]["teams"][0]["source"] == "dilar"
    assert result[0]["teams"][0]["chapter_page"] == ["b.jpg"]
