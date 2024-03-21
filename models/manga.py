from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Dict

class ChapterTeam(BaseModel):
    team_name: str
    chapter_date: str
    chapter_page: List[str]

class MangaInfo(BaseModel):
    title: str
    summary: str
    cover: str
    id: int
    year: int
    rate: float
    associated: List[str]
    latest_chapter: str
    categories: List[str]
    status: str
    type: str

def manga_info_response(title: str, summary: str, cover: str, manga_id: int, year: int, rate: float, 
                               associated: List[str], latest_chapter: str, categories: List[str], status: str, 
                               type: str, chapters_info: Dict[str, List[ChapterTeam]]) -> MangaInfo:
    return MangaInfo(
        title=title,
        summary=summary,
        cover=cover,
        id=manga_id,
        year=year,
        rate=round(rate, 1),
        associated=associated,
        latest_chapter=latest_chapter,
        categories=categories,
        status=status,
        type=type,
        chapters=chapters_info
    )
