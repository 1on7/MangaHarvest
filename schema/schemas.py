def mangaInfo(info) -> dict:
  return {
    "id": str(info["_id"]),
    "title": info["title"],
    "description": info["summary"],
    "year": info["year"],
    "rate": info["rate"],
    "associated": info["associated"],
    "latest_chapter": info["latest_chapter"],
    "categories": info["categories"],
    "status": info["status"],
    "type": info["type"]
  }

def list_mangaInfo(list_info) -> list:
  return [mangaInfo(info) for info in list_info]

def mangaChapters(chapter) -> dict:
  return {
    "id": chapter["manga_id"],
    "chapters": chapter["chapters"]
  }