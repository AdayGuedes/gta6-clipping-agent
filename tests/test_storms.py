import pytest

from src.models import ChatEvent
from src.storms import (
    DISTINCT_SHARE_MAX,
    STORM_GAP_S,
    Storm,
    StormReport,
    distinct_share,
    measure_storms,
    normalize_message,
)

WINDOW_S = 60


def events_at(second, messages):
    return [ChatEvent(t_s=float(second), message=message) for message in messages]


def varied(second, count, prefix="m"):
    return events_at(second, [f"{prefix}{i}" for i in range(count)])


def repeated(second, count, message="!sorteo"):
    return events_at(second, [message] * count)


def test_thresholds_are_the_documented_ones():
    assert DISTINCT_SHARE_MAX == 0.35
    assert STORM_GAP_S == 300


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("  !Sorteo  ", "!sorteo"),
        ("hola   mundo", "hola mundo"),
        ("HOLA\tMUNDO", "hola mundo"),
        ("dancer \u034f", "dancer"),
        ("gol\u200b", "gol"),
        ("\uff21\uff22", "ab"),
    ],
)
def test_normalize_message(raw, expected):
    assert normalize_message(raw) == expected


def test_normalize_message_keeps_accents():
    assert normalize_message("Qué PASÓ") == "qué pasó"


def test_distinct_share_of_all_different_messages_is_one():
    assert distinct_share(["a", "b", "c", "d"]) == 1.0


def test_distinct_share_of_identical_messages_is_one_over_n():
    assert distinct_share(["a"] * 4) == 0.25


def test_distinct_share_of_nothing_is_one():
    assert distinct_share([]) == 1.0


def test_a_peak_of_varied_messages_is_not_a_storm():
    events = varied(100, 50)

    report = measure_storms(events, [100], WINDOW_S)

    assert report == StormReport(peaks=1, flagged=0, largest=None)
    assert report.largest_size == 0
    assert report.share == 0.0


def test_a_peak_of_repeated_messages_is_a_storm_of_one():
    events = repeated(100, 50)

    report = measure_storms(events, [100], WINDOW_S)

    assert report.flagged == 1
    assert report.largest == Storm(
        peaks=(100,), start_s=100, end_s=160, top_message="!sorteo"
    )
    assert report.largest_size == 1
    assert report.share == 1.0


def test_the_peak_window_is_half_open_on_the_right():
    inside = repeated(159, 10)
    outside = varied(160, 100)

    report = measure_storms(inside + outside, [100], WINDOW_S)

    assert report.flagged == 1


def test_messages_before_the_peak_are_ignored():
    before = varied(99, 100)
    after = repeated(100, 10)

    report = measure_storms(before + after, [100], WINDOW_S)

    assert report.flagged == 1


def test_the_distinct_threshold_is_inclusive():
    texts = ["a"] * 14 + [f"u{i}" for i in range(6)]
    assert distinct_share(texts) == pytest.approx(0.35)
    events = events_at(100, texts)

    report = measure_storms(events, [100], WINDOW_S)

    assert report.flagged == 1


def test_just_above_the_distinct_threshold_is_not_flagged():
    texts = ["a"] * 13 + [f"u{i}" for i in range(7)]
    events = events_at(100, texts)

    report = measure_storms(events, [100], WINDOW_S)

    assert report.flagged == 0


def test_flagged_peaks_close_in_time_form_one_storm():
    events = []
    for second in (1000, 1200, 1400):
        events += repeated(second, 30)

    report = measure_storms(events, [1400, 1000, 1200], WINDOW_S)

    assert report.peaks == 3
    assert report.flagged == 3
    assert report.largest.peaks == (1000, 1200, 1400)
    assert (report.largest.start_s, report.largest.end_s) == (1000, 1460)
    assert report.share == 1.0


def test_a_gap_of_exactly_the_storm_gap_still_joins_the_storm():
    events = repeated(1000, 30) + repeated(1000 + STORM_GAP_S, 30)

    report = measure_storms(events, [1000, 1000 + STORM_GAP_S], WINDOW_S)

    assert report.largest_size == 2


def test_a_gap_above_the_storm_gap_splits_the_storm():
    later = 1000 + STORM_GAP_S + 1
    events = repeated(1000, 30) + repeated(later, 30)

    report = measure_storms(events, [1000, later], WINDOW_S)

    assert report.flagged == 2
    assert report.largest_size == 1


def test_an_unflagged_peak_between_two_flagged_ones_does_not_bridge_them():
    events = repeated(1000, 30) + varied(1200, 30) + repeated(1400, 30)

    report = measure_storms(events, [1000, 1200, 1400], WINDOW_S)

    assert report.flagged == 2
    assert report.largest_size == 1


def test_the_largest_storm_wins_and_ties_keep_the_earliest():
    events = []
    for second in (1000, 1200, 5000, 5200, 5400):
        events += repeated(second, 30)

    report = measure_storms(events, [1000, 1200, 5000, 5200, 5400], WINDOW_S)

    assert report.largest.peaks == (5000, 5200, 5400)
    assert report.share == pytest.approx(3 / 5)

    tie = measure_storms(events, [1000, 1200, 5000, 5200], WINDOW_S)

    assert tie.largest.peaks == (1000, 1200)


def test_the_dominant_message_is_the_most_frequent_across_the_storm():
    events = repeated(1000, 20, "!a") + repeated(1000, 5, "!b")
    events += repeated(1200, 20, "!b") + repeated(1200, 12, "!a")

    report = measure_storms(events, [1000, 1200], WINDOW_S)

    assert report.largest.top_message == "!a"


def test_messages_are_compared_after_normalization():
    events = events_at(100, ["!Sorteo", " !sorteo ", "!SORTEO", "!sorteo\u034f"] * 5)

    report = measure_storms(events, [100], WINDOW_S)

    assert report.flagged == 1
    assert report.largest.top_message == "!sorteo"


def test_a_peak_without_messages_is_never_flagged():
    report = measure_storms(varied(5000, 10), [100], WINDOW_S)

    assert report.flagged == 0


def test_no_peaks_gives_an_empty_report():
    report = measure_storms(varied(100, 10), [], WINDOW_S)

    assert report == StormReport(peaks=0, flagged=0, largest=None)
    assert report.share == 0.0


def test_the_threshold_and_gap_can_be_overridden():
    texts = ["a"] * 8 + [f"u{i}" for i in range(12)]
    events = events_at(1000, texts) + events_at(1500, texts)

    strict = measure_storms(events, [1000, 1500], WINDOW_S)
    loose = measure_storms(
        events, [1000, 1500], WINDOW_S, distinct_share_max=0.7, gap_s=600
    )

    assert strict.flagged == 0
    assert loose.largest_size == 2


def test_peaks_are_not_modified():
    peaks = [1200, 1000]

    measure_storms(repeated(1000, 30) + repeated(1200, 30), peaks, WINDOW_S)

    assert peaks == [1200, 1000]
