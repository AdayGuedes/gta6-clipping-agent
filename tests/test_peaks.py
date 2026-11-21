import dataclasses
import itertools

import pytest

from src.models import ChatEvent
from src.peaks import (
    BASELINES,
    LEAD_S,
    MAX_CANDIDATES,
    MERGE_GAP_S,
    TAIL_S,
    WINDOW_S,
    DetectorConfig,
    InsufficientChatError,
    candidate_window,
    compute_baseline,
    count_messages_per_second,
    generate_candidates,
    reaction_points,
    select_peaks,
    to_msg_min,
    window_sums,
)


def event(t_s):
    return ChatEvent(t_s=t_s, message="x")


def uniform_chat(duration_s, every_s=5):
    return [event(float(t)) for t in range(0, duration_s, every_s)]


def burst(at_s, count):
    return [event(float(at_s)) for _ in range(count)]


def summary(candidates):
    return [(c.start_s, c.end_s, c.msg_min) for c in candidates]


def sums_with(length, values):
    sums = [0] * length
    for position, value in values.items():
        sums[position] = value
    return sums


def test_module_constants_match_the_decision():
    assert WINDOW_S == 60
    assert LEAD_S == 60
    assert TAIL_S == 15
    assert MERGE_GAP_S == 120
    assert MAX_CANDIDATES == 20
    assert BASELINES == ("global",)


def test_insufficient_chat_error_is_a_value_error():
    assert issubclass(InsufficientChatError, ValueError)


def test_detector_config_defaults():
    config = DetectorConfig()

    assert config.window_s == 60
    assert config.baseline == "global"
    assert config.top_k == 20
    assert config.min_separation_s == 120
    assert config.lead_s == 60
    assert config.tail_s == 15


def test_detector_config_is_frozen():
    config = DetectorConfig()

    with pytest.raises(dataclasses.FrozenInstanceError):
        config.top_k = 5


def test_detector_config_accepts_custom_values():
    config = DetectorConfig(
        window_s=30, top_k=3, min_separation_s=0, lead_s=0, tail_s=0
    )

    assert (config.window_s, config.top_k, config.min_separation_s) == (30, 3, 0)
    assert (config.lead_s, config.tail_s) == (0, 0)


@pytest.mark.parametrize(
    "overrides",
    [
        {"window_s": 0},
        {"window_s": -60},
        {"top_k": 0},
        {"top_k": -1},
        {"min_separation_s": -1},
        {"lead_s": -1},
        {"tail_s": -1},
    ],
)
def test_detector_config_rejects_out_of_range_values(overrides):
    with pytest.raises(ValueError):
        DetectorConfig(**overrides)


@pytest.mark.parametrize(
    "overrides",
    [
        {"window_s": True},
        {"top_k": True},
        {"min_separation_s": False},
        {"lead_s": False},
        {"tail_s": True},
    ],
)
def test_detector_config_rejects_booleans(overrides):
    with pytest.raises(ValueError):
        DetectorConfig(**overrides)


@pytest.mark.parametrize(
    "overrides",
    [
        {"window_s": 60.0},
        {"top_k": "20"},
        {"min_separation_s": 1.5},
        {"lead_s": None},
        {"tail_s": "15"},
    ],
)
def test_detector_config_rejects_non_integers(overrides):
    with pytest.raises(ValueError):
        DetectorConfig(**overrides)


@pytest.mark.parametrize("baseline", ["local", "rolling", "", "Global"])
def test_detector_config_rejects_unknown_baselines(baseline):
    with pytest.raises(ValueError, match="baseline"):
        DetectorConfig(baseline=baseline)


def test_count_floors_timestamps_into_one_second_buckets():
    events = [event(0), event(0.9), event(1), event(59.999)]

    counts = count_messages_per_second(events)

    assert len(counts) == 60
    assert counts[0] == 2
    assert counts[1] == 1
    assert counts[59] == 1
    assert sum(counts) == 4


def test_count_accepts_unsorted_input():
    events = [event(3), event(0), event(3), event(1)]

    assert count_messages_per_second(events) == [1, 1, 0, 2]


def test_count_fills_silent_seconds_up_to_the_last_event():
    assert count_messages_per_second([event(2), event(5)]) == [0, 0, 1, 0, 0, 1]


def test_count_without_events_is_empty():
    assert count_messages_per_second([]) == []


def test_count_accepts_any_iterable():
    assert count_messages_per_second(event(t) for t in (0, 1, 1)) == [1, 2]


def test_window_sums_slide_one_second_at_a_time():
    assert window_sums([1, 2, 3, 4, 5], 2) == [3, 5, 7, 9]
    assert window_sums([1, 2, 3, 4, 5], 3) == [6, 9, 12]


def test_window_sums_with_a_one_second_window_return_the_counts():
    assert window_sums([4, 0, 7], 1) == [4, 0, 7]


def test_window_sums_have_one_position_per_complete_window():
    assert len(window_sums([1] * 100, 60)) == 41
    assert len(window_sums([1] * 60, 60)) == 1


def test_window_sums_of_a_chat_as_long_as_the_window_is_the_total():
    assert window_sums([1, 2, 3, 4, 5], 5) == [15]


def test_window_sums_of_a_chat_shorter_than_the_window_is_a_single_window():
    assert window_sums([1, 2, 3], 60) == [6]


def test_window_sums_without_counts_is_empty():
    assert window_sums([], 60) == []


@pytest.mark.parametrize(
    ("window_sum", "window_s", "expected"),
    [
        (60, 60, 60.0),
        (30, 30, 60.0),
        (6, 30, 12.0),
        (0, 60, 0.0),
        (1, 120, 0.5),
        (5, 120, 2.5),
    ],
)
def test_to_msg_min_scales_the_window_sum_to_one_minute(window_sum, window_s, expected):
    assert to_msg_min(window_sum, window_s) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("rates", "expected"),
    [
        ([3.0, 5.0, 10.0], 5.0),
        ([2.0, 4.0, 6.0, 8.0], 5.0),
        ([10.0] * 9 + [40.0], 10.0),
        ([7.5], 7.5),
    ],
)
def test_baseline_is_the_median(rates, expected):
    assert compute_baseline(rates) == pytest.approx(expected)


def test_baseline_falls_back_to_the_mean_when_the_median_is_zero():
    assert compute_baseline([0.0, 0.0, 0.0, 4.0, 6.0]) == pytest.approx(2.0)
    assert compute_baseline([0.0, 0.0, 5.0]) == pytest.approx(5 / 3)


@pytest.mark.parametrize("rates", [[], [0.0], [0.0, 0.0, 0.0]])
def test_baseline_without_activity_raises(rates):
    with pytest.raises(InsufficientChatError, match="^chat sin actividad suficiente$"):
        compute_baseline(rates)


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


def test_candidate_window_extends_from_lead_before_to_window_plus_tail_after():
    assert candidate_window(100, DetectorConfig()) == (40, 175)


def test_candidate_window_is_clipped_to_zero_by_the_lead():
    config = DetectorConfig()

    assert candidate_window(0, config) == (0, 75)
    assert candidate_window(59, config) == (0, 134)
    assert candidate_window(60, config) == (0, 135)
    assert candidate_window(61, config) == (1, 136)


def test_candidate_window_follows_the_config():
    config = DetectorConfig(window_s=30, lead_s=10, tail_s=5)

    assert candidate_window(100, config) == (90, 135)
    assert candidate_window(4, config) == (0, 39)


def test_candidate_window_without_lead_or_tail_is_the_window_itself():
    config = DetectorConfig(lead_s=0, tail_s=0)

    assert candidate_window(100, config) == (100, 160)


def test_select_peaks_returns_the_highest_sums_first():
    assert select_peaks([1, 5, 1, 9, 1, 3], top_k=3, min_separation_s=2) == [3, 1, 5]


def test_select_peaks_allows_exactly_the_minimum_separation():
    sums = sums_with(400, {10: 9, 130: 8})

    assert select_peaks(sums, top_k=5, min_separation_s=120) == [10, 130]


def test_select_peaks_suppresses_one_second_inside_the_separation():
    sums = sums_with(400, {10: 9, 129: 8})

    assert select_peaks(sums, top_k=5, min_separation_s=120) == [10]


def test_select_peaks_suppression_is_symmetric_around_a_peak():
    sums = sums_with(400, {200: 9, 81: 8, 319: 8})

    assert select_peaks(sums, top_k=5, min_separation_s=120) == [200]


def test_select_peaks_suppresses_against_kept_peaks_only_not_in_a_chain():
    sums = sums_with(400, {100: 10, 150: 9, 230: 8})

    assert select_peaks(sums, top_k=5, min_separation_s=120) == [100, 230]


def test_select_peaks_breaks_ties_with_the_smaller_start():
    sums = sums_with(400, {300: 7, 50: 7, 200: 7})

    assert select_peaks(sums, top_k=2, min_separation_s=120) == [50, 200]


def test_select_peaks_on_a_plateau_keeps_the_first_position_only():
    sums = sums_with(300, {position: 5 for position in range(10, 21)})

    assert select_peaks(sums, top_k=5, min_separation_s=120) == [10]


def test_select_peaks_with_tied_sums_inside_the_separation_keeps_the_earlier():
    sums = sums_with(400, {100: 7, 219: 7})

    assert select_peaks(sums, top_k=5, min_separation_s=120) == [100]


def test_select_peaks_stops_at_top_k():
    sums = sums_with(1000, {100: 5, 300: 9, 500: 7, 700: 8, 900: 6})

    assert select_peaks(sums, top_k=2, min_separation_s=120) == [300, 700]
    assert select_peaks(sums, top_k=10, min_separation_s=120) == [
        300,
        700,
        500,
        900,
        100,
    ]


def test_select_peaks_never_emits_zero_sums():
    assert select_peaks([0, 0, 3, 0], top_k=5, min_separation_s=0) == [2]
    assert select_peaks([0, 0, 0], top_k=5, min_separation_s=0) == []


def test_select_peaks_without_sums_is_empty():
    assert select_peaks([], top_k=5, min_separation_s=120) == []


@pytest.mark.parametrize("min_separation_s", [0, 1])
def test_select_peaks_with_no_real_separation_keeps_every_active_position(
    min_separation_s,
):
    assert select_peaks([3, 2, 1], top_k=5, min_separation_s=min_separation_s) == [
        0,
        1,
        2,
    ]


def test_a_single_message_still_gives_one_candidate():
    [candidate] = generate_candidates([event(0)])

    assert (candidate.start_s, candidate.end_s) == (0.0, 75.0)
    assert candidate.msg_min == 1
    assert candidate.multiplier == pytest.approx(1.0)
    assert candidate.reaction_points == pytest.approx(0.0)


def test_chat_shorter_than_the_window_gives_a_single_window_candidate():
    [candidate] = generate_candidates([event(0), event(10), event(20)])

    assert (candidate.start_s, candidate.end_s) == (0.0, 75.0)
    assert candidate.msg_min == 3
    assert candidate.multiplier == pytest.approx(1.0)


def test_chat_shorter_than_a_custom_window_scales_msg_min_to_one_minute():
    config = DetectorConfig(window_s=30)

    [candidate] = generate_candidates([event(0), event(10), event(20)], config=config)

    assert (candidate.start_s, candidate.end_s) == (0.0, 45.0)
    assert candidate.msg_min == 6
    assert candidate.multiplier == pytest.approx(1.0)


def test_flat_chat_returns_candidates_with_no_reaction_points():
    candidates = generate_candidates(uniform_chat(600))

    assert summary(candidates) == [
        (0.0, 75.0, 12),
        (60.0, 195.0, 12),
        (180.0, 315.0, 12),
        (300.0, 435.0, 12),
        (420.0, 555.0, 12),
    ]
    assert all(c.multiplier == pytest.approx(1.0) for c in candidates)
    assert all(c.reaction_points == pytest.approx(0.0) for c in candidates)


def test_flat_chat_candidates_are_spaced_by_the_minimum_separation():
    candidates = generate_candidates(uniform_chat(3000))

    assert [c.start_s for c in candidates] == [0.0] + [
        float(120 * k - 60) for k in range(1, 20)
    ]


def test_empty_chat_raises():
    with pytest.raises(InsufficientChatError, match="chat sin actividad suficiente"):
        generate_candidates([])


def test_empty_iterator_raises():
    with pytest.raises(InsufficientChatError, match="chat sin actividad suficiente"):
        generate_candidates(iter([]))


def test_events_may_come_from_a_generator():
    events = (event(float(t)) for t in range(0, 600, 5))

    assert summary(generate_candidates(events)) == summary(
        generate_candidates(uniform_chat(600))
    )


def test_clear_peak_is_the_first_candidate_with_its_exact_numbers():
    events = uniform_chat(600) + burst(300, 48)

    first, *rest = generate_candidates(events)

    assert (first.start_s, first.end_s) == (181.0, 316.0)
    assert first.msg_min == 60
    assert first.multiplier == pytest.approx(5.0)
    assert first.reaction_points == pytest.approx(29.0)
    assert all(c.msg_min == 12 for c in rest)
    assert all(c.reaction_points == pytest.approx(0.0) for c in rest)


def test_peak_window_starts_at_the_first_second_that_covers_the_burst():
    events = uniform_chat(1200) + burst(700, 36)

    [first, *_] = generate_candidates(events)

    assert first.start_s == 700 - 59 - 60
    assert first.end_s == 700 - 59 + 60 + 15
    assert first.msg_min == 48
    assert first.multiplier == pytest.approx(4.0)
    assert first.reaction_points == pytest.approx(28.0)


def test_peak_near_the_start_clips_the_window_to_zero():
    events = uniform_chat(600) + burst(100, 18)

    [first, *_] = generate_candidates(events)

    assert (first.start_s, first.end_s) == (0.0, 116.0)
    assert first.msg_min == 30
    assert first.multiplier == pytest.approx(2.5)
    assert first.reaction_points == pytest.approx(21.0)


def test_peak_in_the_first_seconds_starts_at_zero():
    events = uniform_chat(600) + burst(10, 48)

    [first, *_] = generate_candidates(events)

    assert (first.start_s, first.end_s) == (0.0, 75.0)
    assert first.msg_min == 60


def test_window_is_not_clipped_at_the_end_of_the_chat():
    events = uniform_chat(600) + burst(590, 48)

    [first, *_] = generate_candidates(events)

    assert first.start_s == 531 - 60
    assert first.end_s == 531 + 75
    assert first.end_s > 595


def test_unsorted_events_give_the_same_candidates():
    events = uniform_chat(600) + burst(300, 48)

    assert generate_candidates(list(reversed(events))) == generate_candidates(events)


def test_baseline_is_the_median_so_a_burst_does_not_raise_it():
    events = uniform_chat(600) + burst(300, 48)

    [first, *_] = generate_candidates(events)

    assert first.multiplier == pytest.approx(60 / 12)


def test_sparse_chat_uses_the_mean_baseline_and_ignores_zero_sum_windows():
    events = [event(0), *burst(300, 1), event(500)]

    candidates = generate_candidates(events)

    assert summary(candidates) == [
        (0.0, 75.0, 1),
        (181.0, 316.0, 1),
        (381.0, 516.0, 1),
    ]
    assert all(c.multiplier == pytest.approx(442 / 62) for c in candidates)
    assert all(c.reaction_points == pytest.approx(30.0) for c in candidates)


def test_output_is_ordered_by_points_descending():
    events = uniform_chat(1500) + burst(300, 18) + burst(700, 48) + burst(1100, 36)

    candidates = generate_candidates(events, max_candidates=3)

    assert [c.msg_min for c in candidates] == [60, 48, 30]
    points = [c.reaction_points for c in candidates]
    assert points == sorted(points, reverse=True)
    assert [c.start_s for c in candidates] == [581.0, 981.0, 181.0]


def test_equal_points_are_ordered_by_ascending_start():
    events = uniform_chat(1500) + burst(1100, 36) + burst(300, 36)

    candidates = generate_candidates(events, max_candidates=2)

    assert [c.start_s for c in candidates] == [181.0, 981.0]
    assert [c.msg_min for c in candidates] == [48, 48]


def test_equal_points_with_different_sums_are_ordered_by_ascending_start():
    events = uniform_chat(1500) + burst(300, 100) + burst(900, 200)

    candidates = generate_candidates(events, max_candidates=2)

    assert [c.reaction_points for c in candidates] == [30.0, 30.0]
    assert [c.msg_min for c in candidates] == [112, 212]
    assert [c.start_s for c in candidates] == [181.0, 781.0]


def test_equal_bursts_119_seconds_apart_emit_the_later_one_from_its_plateau():
    events = uniform_chat(1500) + burst(500, 36) + burst(619, 36)

    candidates = generate_candidates(events, max_candidates=2)

    assert [(c.start_s, c.end_s, c.msg_min) for c in candidates] == [
        (381.0, 516.0, 48),
        (501.0, 636.0, 48),
    ]


def test_default_top_k_is_twenty_and_keeps_the_strongest_peaks():
    events = uniform_chat(7600)
    for k in range(25):
        events += burst(300 * k + 200, 20 + k)

    candidates = generate_candidates(events)

    assert len(candidates) == 20
    assert [c.start_s for c in candidates] == [
        300 * k + 200 - 59 - 60 for k in range(24, 4, -1)
    ]
    assert [c.msg_min for c in candidates] == [32 + k for k in range(24, 4, -1)]


def test_max_candidates_limits_the_result():
    events = uniform_chat(3000)
    for k in range(5):
        events += burst(400 * k + 200, 40)

    assert len(generate_candidates(events, max_candidates=3)) == 3


@pytest.mark.parametrize("max_candidates", [0, -1])
def test_max_candidates_must_be_at_least_one(max_candidates):
    with pytest.raises(ValueError, match="max_candidates"):
        generate_candidates(uniform_chat(600), max_candidates=max_candidates)


def test_max_candidates_above_top_k_is_capped_by_top_k():
    events = uniform_chat(3000)
    config = DetectorConfig(top_k=3)

    candidates = generate_candidates(events, max_candidates=10, config=config)

    assert len(candidates) == 3


def test_max_candidates_below_top_k_wins():
    events = uniform_chat(3000)
    config = DetectorConfig(top_k=10)

    candidates = generate_candidates(events, max_candidates=2, config=config)

    assert len(candidates) == 2


def test_top_k_from_the_config_applies_without_max_candidates():
    events = uniform_chat(3000)

    assert len(generate_candidates(events, config=DetectorConfig(top_k=4))) == 4


def test_fewer_positions_than_top_k_return_what_fits():
    assert len(generate_candidates(uniform_chat(600))) == 5


def test_custom_min_separation_changes_how_many_peaks_fit():
    events = uniform_chat(600)

    close = generate_candidates(events, config=DetectorConfig(min_separation_s=60))
    far = generate_candidates(events, config=DetectorConfig(min_separation_s=240))

    assert len(close) == 9
    assert len(far) == 3


def test_custom_window_scales_msg_min_and_the_candidate_window():
    events = uniform_chat(600) + burst(300, 24)
    config = DetectorConfig(window_s=30)

    [first, *_] = generate_candidates(events, config=config)

    assert (first.start_s, first.end_s) == (211.0, 316.0)
    assert first.msg_min == 60
    assert first.multiplier == pytest.approx(5.0)
    assert first.reaction_points == pytest.approx(29.0)


def test_custom_lead_and_tail_shape_the_candidate_window():
    events = uniform_chat(600) + burst(300, 48)
    config = DetectorConfig(lead_s=10, tail_s=0)

    [first, *_] = generate_candidates(events, config=config)

    assert (first.start_s, first.end_s) == (231.0, 301.0)


def test_msg_min_rounds_half_up():
    events = [event(0), event(1), event(2), event(3), event(4)]
    config = DetectorConfig(window_s=120)

    [candidate] = generate_candidates(events, config=config)

    assert candidate.msg_min == 3


def test_msg_min_rounds_half_up_for_a_half_below_one():
    config = DetectorConfig(window_s=120)

    [candidate] = generate_candidates([event(0)], config=config)

    assert candidate.msg_min == 1


def test_multiplier_uses_the_unrounded_msg_min():
    events = uniform_chat(600) + burst(300, 7)
    config = DetectorConfig(window_s=40)

    [first, *_] = generate_candidates(events, config=config)

    assert first.msg_min == 23
    assert first.multiplier == pytest.approx(22.5 / 12)
    assert first.multiplier != pytest.approx(23 / 12)
    assert first.reaction_points == pytest.approx(11 + (22.5 / 12 - 1.5) * 9)


@pytest.mark.parametrize(("gap_s", "overlap_s"), [(120, 15), (125, 10), (134, 1)])
def test_peaks_just_past_the_separation_are_two_candidates_with_overlapping_windows(
    gap_s, overlap_s
):
    events = uniform_chat(1500) + burst(500, 30) + burst(500 + gap_s, 40)

    candidates = generate_candidates(events, max_candidates=2)
    by_start = sorted(candidates, key=lambda c: c.start_s)

    assert [c.msg_min for c in candidates] == [52, 42]
    assert len(candidates) == 2
    first, second = by_start
    assert second.start_s - first.start_s == gap_s
    assert first.end_s - second.start_s == overlap_s


def test_weaker_burst_119_seconds_before_a_stronger_one_is_suppressed():
    events = uniform_chat(1500) + burst(500, 30) + burst(500 + 119, 40)

    candidates = generate_candidates(events)

    assert 52 in [c.msg_min for c in candidates]
    assert 42 not in [c.msg_min for c in candidates]


def test_a_long_run_of_peaks_is_never_merged_into_one_long_window():
    events = uniform_chat(3000)
    for k in range(10):
        events += burst(300 + 130 * k, 30)

    candidates = generate_candidates(events, max_candidates=10)

    by_start = sorted(candidates, key=lambda c: c.start_s)

    assert len(candidates) == 10
    assert all(c.end_s - c.start_s == 135 for c in candidates)
    assert all(
        earlier.end_s - later.start_s == 5
        for earlier, later in itertools.pairwise(by_start)
    )
