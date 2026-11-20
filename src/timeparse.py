import math
import re

_HHMMSS = re.compile(r"([0-9]{2,}):([0-5][0-9]):([0-5][0-9])")


class InvalidTime(ValueError):
    pass


def hhmmss_to_seconds(text: str) -> int:
    match = _HHMMSS.fullmatch(text)
    if match is None:
        raise InvalidTime(
            f"expected HH:MM:SS (hours with two or more digits), got {text!r}"
        )
    hours, minutes, seconds = (int(group) for group in match.groups())
    return hours * 3600 + minutes * 60 + seconds


def seconds_to_hhmmss(seconds: float) -> str:
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)):
        raise InvalidTime(f"expected a number of seconds, got {seconds!r}")
    if not math.isfinite(seconds) or seconds < 0:
        raise InvalidTime(f"time must be finite and non-negative, got {seconds!r}")
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def parse_time(value: object) -> float:
    if isinstance(value, bool) or value is None:
        raise InvalidTime(f"expected seconds or HH:MM:SS, got {value!r}")

    if isinstance(value, (int, float)):
        seconds = float(value)
    elif isinstance(value, str):
        text = value.strip()
        if ":" in text:
            return float(hhmmss_to_seconds(text))
        try:
            seconds = float(text)
        except ValueError:
            raise InvalidTime(f"expected seconds or HH:MM:SS, got {value!r}") from None
    else:
        raise InvalidTime(f"expected seconds or HH:MM:SS, got {type(value).__name__}")

    if not math.isfinite(seconds) or seconds < 0:
        raise InvalidTime(f"time must be finite and non-negative, got {value!r}")
    return seconds
