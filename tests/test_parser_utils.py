from bs4 import BeautifulSoup

from MangaSite.parser_utils import best_match, chapter_number, extract_image_urls


def test_chapter_number_prefers_explicit_chapter_label():
    assert chapter_number("Read Chapter 128.5") == 128.5
    assert chapter_number("الفصل 128") == 128


def test_chapter_number_can_use_chapter_url():
    assert chapter_number("Next", href="https://example.com/chapter-42") == 42


def test_extract_image_urls_supports_lazy_loading_and_srcset():
    soup = BeautifulSoup(
        """
        <img data-src="/images/1.jpg">
        <img data-lazy-src="/images/2.jpg">
        <img src="/images/3.jpg" srcset="/images/3-small.jpg 480w, /images/3.jpg 1080w">
        """,
        "html.parser",
    )
    assert extract_image_urls(soup, base_url="https://example.com/") == [
        "https://example.com/images/1.jpg",
        "https://example.com/images/2.jpg",
        "https://example.com/images/3.jpg",
        "https://example.com/images/3-small.jpg",
    ]


def test_best_match_does_not_blindly_take_first_result():
    items = [
        {"title": "Solo Leveling Ragnarok", "url": "https://example/1"},
        {"title": "Solo Leveling", "url": "https://example/2"},
    ]
    assert best_match(items, "Solo Leveling")["url"] == "https://example/2"
