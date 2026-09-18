from utils.title import normalize_title, title_similarity


def test_normalize_title():
    assert normalize_title("  Solo-Leveling_  ") == "solo leveling"


def test_title_similarity_exact():
    assert title_similarity("Solo Leveling", "solo-leveling") == 1.0


def test_title_similarity_rejects_unrelated():
    assert title_similarity("Solo Leveling", "Naruto") == 0.0
