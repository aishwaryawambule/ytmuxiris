from ytmuxiris.utils.helpers import format_duration, parse_duration, truncate_text


def test_format_duration_zero():
    assert format_duration(0) == "0:00"


def test_format_duration_minutes():
    assert format_duration(225) == "3:45"


def test_format_duration_hours():
    assert format_duration(3723) == "1:02:03"


def test_parse_duration_minutes():
    assert parse_duration("3:45") == 225


def test_parse_duration_hours():
    assert parse_duration("1:02:03") == 3723


def test_parse_duration_none():
    assert parse_duration(None) == 0


def test_parse_duration_empty():
    assert parse_duration("") == 0


def test_truncate_short():
    assert truncate_text("hello", 10) == "hello"


def test_truncate_long():
    result = truncate_text("hello world", 8)
    assert len(result) <= 8
    assert result.endswith("…")
