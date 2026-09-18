from typing import List, Optional

from pydantic import BaseModel, Field


class ChapterTeam(BaseModel):
    team_name: str
    chapter_date: str = ""
    chapter_page: List[str] = Field(default_factory=list)
    source: str = ""
    verification_status: str = "unverified"
    last_verified_at: Optional[str] = None


class MangaInfo(BaseModel):
    title: str
    summary: str = ""
    cover: str = ""
    id: str
    year: Optional[int] = None
    rate: Optional[float] = None
    associated: List[str] = Field(default_factory=list)
    latest_chapter: Optional[float] = None
    categories: List[str] = Field(default_factory=list)
    status: str = ""
    type: str = ""
