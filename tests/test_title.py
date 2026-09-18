from utils.title import normalize_title, title_similarity


def test_normalize_title():
    assert normalize_title("  Solo-Leveling_  ") == "solo leveling"


def test_title_similarity_exact():
    assert title_similarity("Solo Leveling", "solo-leveling") == 1.0


def test_title_similarity_rejects_unrelated():
    assert title_similarity("Solo Leveling", "Naruto") == 0.0


def test_title_similarity_partial_token_match():
    assert title_similarity("Solo Leveling", "Solo Leveling Ragnarok") > 0.75


def test_title_search_regex_is_safe_and_token_aware():
    from utils.title import title_search_regex
    assert title_search_regex("Solo Leveling") == "solo.*leveling"
    assert title_search_regex("[test]") == r"\\[test\\]"
