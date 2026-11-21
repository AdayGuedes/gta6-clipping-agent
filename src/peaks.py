import math
import statistics
from collections.abc import Iterable
from dataclasses import dataclass

from src.models import Candidate, ChatEvent

WINDOW_S = 60
LEAD_S = 60
TAIL_S = 15
MERGE_GAP_S = 120
MAX_CANDIDATES = 20
BASELINES = ("global",)

_REACTION_TIERS = (
    (1.0, 1.5, 0.0, 10.0),
    (1.5, 2.5, 11.0, 20.0),
    (2.5, 4.0, 21.0, 27.0),
    (4.0, 6.0, 28.0, 30.0),
)


class InsufficientChatError(ValueError):
    pass


def _require_int(name: str, value: object, minimum: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}, got {value!r}")


@dataclass(frozen=True)
class DetectorConfig:
    window_s: int = WINDOW_S
    baseline: str = "global"
    top_k: int = MAX_CANDIDATES
    min_separation_s: int = MERGE_GAP_S
    lead_s: int = LEAD_S
    tail_s: int = TAIL_S

    def __post_init__(self) -> None:
        _require_int("window_s", self.window_s, 1)
        _require_int("top_k", self.top_k, 1)
        _require_int("min_separation_s", self.min_separation_s, 0)
        _require_int("lead_s", self.lead_s, 0)
        _require_int("tail_s", self.tail_s, 0)
        if self.baseline not in BASELINES:
            raise ValueError(
                f"baseline must be one of {BASELINES}, got {self.baseline!r}"
            )


def count_messages_per_second(events: Iterable[ChatEvent]) -> list[int]:
    seconds = [int(event.t_s) for event in events]
    if not seconds:
        return []
    counts = [0] * (max(seconds) + 1)
    for second in seconds:
        counts[second] += 1
    return counts


def window_sums(counts: list[int], window_s: int) -> list[int]:
    if not counts:
        return []
    prefix = [0]
    for count in counts:
        prefix.append(prefix[-1] + count)
    if len(counts) < window_s:
        return [prefix[-1]]
    return [prefix[p + window_s] - prefix[p] for p in range(len(counts) - window_s + 1)]


def to_msg_min(window_sum: int, window_s: int) -> float:
    return window_sum * 60 / window_s


def compute_baseline(rates: list[float]) -> float:
    if rates:
        median = statistics.median(rates)
        if median > 0:
            return float(median)
        mean = statistics.fmean(rates)
        if mean > 0:
            return mean
    raise InsufficientChatError("chat sin actividad suficiente")


def reaction_points(multiplier: float) -> float:
    if math.isnan(multiplier) or multiplier < 0:
        raise ValueError(
            f"multiplier must be a non-negative number, got {multiplier!r}"
        )
    for low, high, points_low, points_high in _REACTION_TIERS:
        if low <= multiplier < high:
            fraction = (multiplier - low) / (high - low)
            return points_low + fraction * (points_high - points_low)
    return 0.0 if multiplier < _REACTION_TIERS[0][0] else 30.0


def candidate_window(peak_start_s: int, config: DetectorConfig) -> tuple[int, int]:
    start_s = max(0, peak_start_s - config.lead_s)
    end_s = peak_start_s + config.window_s + config.tail_s
    return start_s, end_s


def separation_gap(min_separation_s: int) -> int:
    return max(min_separation_s, 1)


def is_separated(position: int, chosen: list[int], min_separation_s: int) -> bool:
    gap = separation_gap(min_separation_s)
    return all(abs(position - kept) >= gap for kept in chosen)


def select_peaks(sums: list[int], top_k: int, min_separation_s: int) -> list[int]:
    order = sorted(range(len(sums)), key=lambda p: (-sums[p], p))
    chosen: list[int] = []
    for position in order:
        if len(chosen) == top_k or sums[position] == 0:
            break
        if is_separated(position, chosen, min_separation_s):
            chosen.append(position)
    return chosen


def generate_candidates(
    events: Iterable[ChatEvent],
    max_candidates: int | None = None,
    config: DetectorConfig | None = None,
) -> list[Candidate]:
    if max_candidates is not None and max_candidates < 1:
        raise ValueError(f"max_candidates must be at least 1, got {max_candidates}")
    if config is None:
        config = DetectorConfig()
    top_k = (
        config.top_k if max_candidates is None else min(max_candidates, config.top_k)
    )

    sums = window_sums(count_messages_per_second(events), config.window_s)
    baseline = compute_baseline([to_msg_min(s, config.window_s) for s in sums])

    peaks = select_peaks(sums, top_k, config.min_separation_s)
    candidates = [_candidate(p, sums[p], baseline, config) for p in peaks]
    candidates.sort(key=lambda c: (-c.reaction_points, c.start_s))
    return candidates


def _candidate(
    peak_start_s: int, window_sum: int, baseline: float, config: DetectorConfig
) -> Candidate:
    msg_min = to_msg_min(window_sum, config.window_s)
    multiplier = msg_min / baseline
    start_s, end_s = candidate_window(peak_start_s, config)
    return Candidate(
        start_s=start_s,
        end_s=end_s,
        msg_min=math.floor(msg_min + 0.5),
        multiplier=multiplier,
        reaction_points=reaction_points(multiplier),
    )
