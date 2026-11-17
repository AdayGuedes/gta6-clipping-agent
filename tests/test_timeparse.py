import pytest

from src.timeparse import InvalidTime, hhmmss_to_seconds, parse_time


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("00:00:00", 0),
        ("00:01:05", 65),
        ("01:23:45", 5025),
        ("100:00:00", 360000),
    ],
)
def test_hhmmss_to_seconds(text, expected):
    assert hhmmss_to_seconds(text) == expected


@pytest.mark.parametrize(
    "text", ["0:05:30", "01:60:00", "01:00:60", "1:2:3", "01:23", "", "abc"]
)
def test_hhmmss_rejects_invalid_formats(text):
    with pytest.raises(ValueError):
        hhmmss_to_seconds(text)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, 0.0),
        (65, 65.0),
        (12.5, 12.5),
        ("00:01:05", 65.0),
        ("65", 65.0),
        (" 12.5 ", 12.5),
    ],
)
def test_parse_time_accepts_numbers_and_hhmmss(value, expected):
    result = parse_time(value)
    assert result == expected
    assert isinstance(result, float)


@pytest.mark.parametrize(
    "value",
    [
        -1,
        -0.5,
        "-3",
        float("nan"),
        float("inf"),
        "nan",
        "inf",
        True,
        None,
        [],
        "",
        "not a time",
    ],
)
def test_parse_time_rejects_invalid_values(value):
    with pytest.raises(ValueError):
        parse_time(value)


def test_invalid_time_is_a_value_error():
    assert issubclass(InvalidTime, ValueError)
