import pytest

from src.timeparse import (
    InvalidTime,
    hhmmss_to_seconds,
    parse_time,
    seconds_to_hhmmss,
)


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


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0, "00:00:00"),
        (65, "00:01:05"),
        (5025, "01:23:45"),
        (360000, "100:00:00"),
        (59.999, "00:00:59"),
        (100.2, "00:01:40"),
    ],
)
def test_seconds_to_hhmmss(seconds, expected):
    assert seconds_to_hhmmss(seconds) == expected


@pytest.mark.parametrize("seconds", [0, 1, 59, 60, 3599, 3600, 5025, 86399, 360000])
def test_seconds_to_hhmmss_is_the_inverse_of_hhmmss_to_seconds(seconds):
    assert hhmmss_to_seconds(seconds_to_hhmmss(seconds)) == seconds


def test_seconds_to_hhmmss_truncates_so_close_times_can_collide():
    assert seconds_to_hhmmss(100.2) == seconds_to_hhmmss(100.4)


@pytest.mark.parametrize(
    "seconds", [-1, -0.5, float("nan"), float("inf"), True, None, "12"]
)
def test_seconds_to_hhmmss_rejects_invalid_values(seconds):
    with pytest.raises(InvalidTime):
        seconds_to_hhmmss(seconds)


def test_invalid_time_is_a_value_error():
    assert issubclass(InvalidTime, ValueError)
