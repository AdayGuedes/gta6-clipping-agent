import math
import statistics
from collections.abc import Iterable

from src.models import Candidate, ChatEvent

BUCKET_S = 60
LEAD_S = 60
TAIL_S = 15
MERGE_GAP_S = 120
CANDIDATE_MIN_MULTIPLIER = 1.5
MAX_CANDIDATES = 20

_REACTION_TIERS = (
    (1.0, 1.5, 0.0, 10.0),
    (1.5, 2.5, 11.0, 20.0),
    (2.5, 4.0, 21.0, 27.0),
    (4.0, 6.0, 28.0, 30.0),
)


class InsufficientChatError(ValueError):
    pass


def count_messages_per_minute(events: Iterable[ChatEvent]) -> list[int]:
    buckets = [int(event.t_s // BUCKET_S) for event in events]
    if not buckets:
        return []
    counts = [0] * (max(buckets) + 1)
    for bucket in buckets:
        counts[bucket] += 1
    return counts


def compute_baseline(counts: list[int]) -> float:
    if counts:
        median = statistics.median(counts)
        if median > 0:
            return float(median)
        mean = statistics.fmean(counts)
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


def generate_candidates(
    events: Iterable[ChatEvent], max_candidates: int = MAX_CANDIDATES
) -> list[Candidate]:
    if max_candidates < 1:
        raise ValueError(f"max_candidates must be at least 1, got {max_candidates}")

    counts = count_messages_per_minute(events)
    baseline = compute_baseline(counts)

    peaks = []
    for bucket, count in enumerate(counts):
        multiplier = count / baseline
        if multiplier >= CANDIDATE_MIN_MULTIPLIER:
            peaks.append(_candidate_for_bucket(bucket, count, multiplier))

    merged = _merge_close_windows(peaks)
    merged.sort(key=lambda candidate: (-candidate.reaction_points, candidate.start_s))
    return merged[:max_candidates]


def _candidate_for_bucket(bucket: int, count: int, multiplier: float) -> Candidate:
    bucket_start = bucket * BUCKET_S
    return Candidate(
        start_s=max(0, bucket_start - LEAD_S),
        end_s=bucket_start + BUCKET_S + TAIL_S,
        msg_min=count,
        multiplier=multiplier,
        reaction_points=reaction_points(multiplier),
    )


def _merge_close_windows(candidates: list[Candidate]) -> list[Candidate]:
    merged: list[Candidate] = []
    for candidate in sorted(candidates, key=lambda c: c.start_s):
        if merged and candidate.start_s - merged[-1].end_s < MERGE_GAP_S:
            merged[-1] = _union(merged[-1], candidate)
        else:
            merged.append(candidate)
    return merged


def _union(first: Candidate, second: Candidate) -> Candidate:
    peak = second if second.msg_min > first.msg_min else first
    return Candidate(
        start_s=min(first.start_s, second.start_s),
        end_s=max(first.end_s, second.end_s),
        msg_min=peak.msg_min,
        multiplier=peak.multiplier,
        reaction_points=peak.reaction_points,
    )
