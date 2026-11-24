import unicodedata
from bisect import bisect_left
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from src.models import ChatEvent

DISTINCT_SHARE_MAX = 0.35
STORM_GAP_S = 300

_INVISIBLE_CATEGORIES = {"Mn", "Cf"}


@dataclass(frozen=True)
class Storm:
    peaks: tuple[int, ...]
    start_s: int
    end_s: int
    top_message: str


@dataclass(frozen=True)
class StormReport:
    peaks: int
    flagged: int
    largest: Storm | None

    @property
    def largest_size(self) -> int:
        return 0 if self.largest is None else len(self.largest.peaks)

    @property
    def share(self) -> float:
        return self.largest_size / self.peaks if self.peaks else 0.0


def normalize_message(message: str) -> str:
    folded = unicodedata.normalize("NFKC", message).lower()
    visible = "".join(
        char
        for char in folded
        if unicodedata.category(char) not in _INVISIBLE_CATEGORIES
    )
    return " ".join(visible.split())


def distinct_share(messages: Sequence[str]) -> float:
    if not messages:
        return 1.0
    return len(set(messages)) / len(messages)


def _window_messages(
    times: list[float], texts: list[str], start_s: int, window_s: int
) -> list[str]:
    low = bisect_left(times, start_s)
    high = bisect_left(times, start_s + window_s)
    return texts[low:high]


def measure_storms(
    events: Iterable[ChatEvent],
    peaks: Sequence[int],
    window_s: int,
    distinct_share_max: float = DISTINCT_SHARE_MAX,
    gap_s: int = STORM_GAP_S,
) -> StormReport:
    ordered = sorted(events, key=lambda event: event.t_s)
    times = [event.t_s for event in ordered]
    texts = [normalize_message(event.message) for event in ordered]

    flagged: list[tuple[int, list[str]]] = []
    for peak in sorted(peaks):
        messages = _window_messages(times, texts, peak, window_s)
        if messages and distinct_share(messages) <= distinct_share_max:
            flagged.append((peak, messages))

    runs: list[list[tuple[int, list[str]]]] = []
    for item in flagged:
        if runs and item[0] - runs[-1][-1][0] <= gap_s:
            runs[-1].append(item)
        else:
            runs.append([item])

    largest = None
    if runs:
        best = max(runs, key=len)
        counts = Counter(message for _, messages in best for message in messages)
        largest = Storm(
            peaks=tuple(peak for peak, _ in best),
            start_s=best[0][0],
            end_s=best[-1][0] + window_s,
            top_message=counts.most_common(1)[0][0],
        )
    return StormReport(peaks=len(peaks), flagged=len(flagged), largest=largest)
