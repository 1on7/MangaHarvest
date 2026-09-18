from utils.date import convert_arabic_date_to_numeric


def test_arabic_date():
    assert convert_arabic_date_to_numeric("يناير 5, 2026") == "2026-01-05"


def test_arabic_digits():
    assert convert_arabic_date_to_numeric("٥ يناير ٢٠٢٦") == "2026-01-05"


def test_invalid_date_is_safe():
    assert convert_arabic_date_to_numeric("not a date") == ""
