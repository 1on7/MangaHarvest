from models.manga import ChapterTeam, MangaInfo


def test_manga_info_defaults():
    manga = MangaInfo(title="Example", id="123")
    assert manga.title == "Example"
    assert manga.id == "123"
    assert manga.categories == []
    assert manga.associated == []


def test_chapter_team_pages_default():
    chapter = ChapterTeam(team_name="team", chapter_date="2026-01-01")
    assert chapter.chapter_page == []
