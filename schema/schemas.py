def mangaInfo(info) -> dict:
    return {
        "id": str(info.get("_id", info.get("id", ""))),
        "title": info.get("title", ""),
        "description": info.get("summary", ""),
        "year": info.get("year"),
        "rate": info.get("rate"),
        "associated": info.get("associated") or [],
        "latest_chapter": info.get("latest_chapter"),
        "categories": info.get("categories") or [],
        "status": info.get("status", ""),
        "type": info.get("type", ""),
    }


def list_mangaInfo(list_info) -> list:
    return [mangaInfo(info) for info in list_info]


def mangaChapters(chapter) -> dict:
    return {
        "id": str(chapter.get("manga_id", "")),
        "chapters": chapter.get("chapters") or [],
    }
