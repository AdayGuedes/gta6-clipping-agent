import pytest

from src.models import ChatEvent
from src.peaks import (
    InsufficientChatError,
    compute_baseline,
    count_messages_per_minute,
    generate_candidates,
    reaction_points,
)


def events_from_counts(counts):
    events = []
    for minute, count in enumerate(counts):
        for k in range(count):
            events.append(ChatEvent(t_s=minute * 60 + k * 60 / count, message="x"))
    return events


def with_peaks(length, peaks, base=10):
    counts = [base] * length
    for minute, count in peaks.items():
        counts[minute] = count
    return counts


def test_count_puts_t_60_in_bucket_1_and_accepts_unsorted_input():
    events = [
        ChatEvent(t_s=125, message="c"),
        ChatEvent(t_s=60.0, message="b"),
        ChatEvent(t_s=0, message="a"),
        ChatEvent(t_s=59.999, message="a"),
    ]
    assert count_messages_per_minute(events) == [2, 1, 1]


def test_count_fills_empty_minutes_up_to_the_last_event():
    events = [ChatEvent(t_s=10, message="a"), ChatEvent(t_s=200, message="b")]
    assert count_messages_per_minute(events) == [1, 0, 0, 1]


def test_count_without_events_is_empty():
    assert count_messages_per_minute([]) == []


@pytest.mark.parametrize(
    ("counts", "expected"),
    [([3, 5, 10], 5.0), ([2, 4, 6, 8], 5.0), ([10] * 9 + [40], 10.0)],
)
def test_baseline_is_the_median(counts, expected):
    assert compute_baseline(counts) == expected


def test_baseline_falls_back_to_the_mean_when_the_median_is_zero():
    assert compute_baseline([0, 0, 0, 4, 6]) == pytest.approx(2.0)


@pytest.mark.parametrize("counts", [[], [0], [0, 0, 0]])
def test_baseline_without_activity_raises(counts):
    with pytest.raises(InsufficientChatError, match="^chat sin actividad suficiente$"):
        compute_baseline(counts)


def test_insufficient_chat_error_is_a_value_error():
    assert issubclass(InsufficientChatError, ValueError)


@pytest.mark.parametrize(
    ("multiplier", "expected"),
    [
        (0.0, 0.0),
        (0.5, 0.0),
        (1.0, 0.0),
        (1.25, 5.0),
        (1.5, 11.0),
        (2.0, 15.5),
        (2.5, 21.0),
        (3.25, 24.0),
        (4.0, 28.0),
        (5.0, 29.0),
        (6.0, 30.0),
        (10.0, 30.0),
    ],
)
def test_reaction_points_follow_the_spec_table(multiplier, expected):
    assert reaction_points(multiplier) == pytest.approx(expected)


def test_reaction_points_jump_at_tier_boundaries():
    assert reaction_points(1.4999) < 10.0
    assert reaction_points(1.5) == pytest.approx(11.0)
    assert reaction_points(2.4999) < 20.0
    assert reaction_points(2.5) == pytest.approx(21.0)


@pytest.mark.parametrize("multiplier", [-0.1, float("nan")])
def test_reaction_points_reject_invalid_multipliers(multiplier):
    with pytest.raises(ValueError):
        reaction_points(multiplier)


def test_clear_peak_produces_one_candidate():
    events = events_from_counts(with_peaks(10, {5: 40}))
    [candidate] = generate_candidates(events)
    assert (candidate.start_s, candidate.end_s) == (240.0, 375.0)
    assert candidate.msg_min == 40
    assert candidate.multiplier == pytest.approx(4.0)
    assert candidate.reaction_points == pytest.approx(28.0)


def test_peak_in_minute_zero_starts_the_window_at_zero():
    events = events_from_counts(with_peaks(10, {0: 40}))
    [candidate] = generate_candidates(events)
    assert (candidate.start_s, candidate.end_s) == (0.0, 75.0)


def test_unsorted_events_give_the_same_candidates():
    events = events_from_counts(with_peaks(10, {5: 40}))
    assert generate_candidates(list(reversed(events))) == generate_candidates(events)


def test_close_peaks_merge_keeping_the_larger_peak():
    events = events_from_counts(with_peaks(20, {5: 30, 8: 50}))
    [candidate] = generate_candidates(events)
    assert (candidate.start_s, candidate.end_s) == (240.0, 555.0)
    assert candidate.msg_min == 50
    assert candidate.multiplier == pytest.approx(5.0)
    assert candidate.reaction_points == pytest.approx(29.0)


def test_merge_keeps_the_larger_peak_when_it_comes_first():
    events = events_from_counts(with_peaks(20, {5: 50, 8: 30}))
    [candidate] = generate_candidates(events)
    assert (candidate.start_s, candidate.end_s, candidate.msg_min) == (240.0, 555.0, 50)


def test_windows_105_s_apart_merge_and_165_s_apart_do_not():
    merged = generate_candidates(events_from_counts(with_peaks(20, {5: 30, 9: 30})))
    separate = generate_candidates(events_from_counts(with_peaks(20, {5: 30, 10: 30})))
    assert len(merged) == 1
    assert len(separate) == 2


def test_far_peaks_give_two_candidates_sorted_by_points():
    events = events_from_counts(with_peaks(20, {2: 30, 15: 50}))
    first, second = generate_candidates(events)
    assert (first.start_s, first.msg_min) == (840.0, 50)
    assert first.reaction_points == pytest.approx(29.0)
    assert (second.start_s, second.msg_min) == (60.0, 30)
    assert second.reaction_points == pytest.approx(23.0)


def test_uniform_chat_gives_no_candidates():
    assert generate_candidates(events_from_counts([10] * 10)) == []


def test_threshold_is_inclusive_at_x1_5():
    [candidate] = generate_candidates(events_from_counts(with_peaks(10, {4: 15})))
    assert candidate.reaction_points == pytest.approx(11.0)
    assert generate_candidates(events_from_counts(with_peaks(10, {4: 14}))) == []


def test_sparse_chat_uses_the_mean_and_the_peak_saturates():
    counts = [0, 1, 1, 0, 0, 0, 0, 20]
    assert compute_baseline(counts) == pytest.approx(2.75)
    [candidate] = generate_candidates(events_from_counts(counts))
    assert (candidate.start_s, candidate.end_s) == (360.0, 495.0)
    assert candidate.msg_min == 20
    assert candidate.multiplier == pytest.approx(20 / 2.75)
    assert candidate.reaction_points == pytest.approx(30.0)


def test_empty_chat_raises():
    with pytest.raises(InsufficientChatError, match="chat sin actividad suficiente"):
        generate_candidates([])


def test_more_than_twenty_peaks_returns_twenty_ordered_by_start_on_ties():
    peaks = {6 * k: 40 for k in range(25)}
    candidates = generate_candidates(events_from_counts(with_peaks(150, peaks)))
    assert len(candidates) == 20
    assert [c.start_s for c in candidates] == [max(0, 360 * k - 60) for k in range(20)]


def test_max_candidates_limits_the_result():
    peaks = {6 * k: 40 for k in range(5)}
    events = events_from_counts(with_peaks(30, peaks))
    assert len(generate_candidates(events, max_candidates=3)) == 3


def test_max_candidates_must_be_positive():
    with pytest.raises(ValueError):
        generate_candidates(
            events_from_counts(with_peaks(10, {5: 40})), max_candidates=0
        )
