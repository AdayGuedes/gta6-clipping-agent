import io
import itertools
import json
import random
import re
import statistics

import pytest

import src.evaluate as evaluate_module
import src.harness as harness_module
import src.judge as judge_module
from src.evaluate import merge_reference
from src.harness import (
    EXIT_FATAL,
    EXIT_INTERRUPTED,
    EXIT_OK,
    MIN_TRIALS,
    SIGNIFICANCE,
    KResult,
    count_hits,
    evaluate_k,
    main,
    passes,
    random_hits,
    run,
    spaced_random_starts,
)
from src.models import ChatEvent, ReferenceClip
from src.peaks import (
    DetectorConfig,
    count_messages_per_second,
    is_separated,
    window_sums,
)

POSITIONS = 5937
PEAK_CONFIG = DetectorConfig(top_k=3)
TRIALS = 200
SEED = 1

NEAR_PEAKS = [(1000, 1030), (3000, 3030), (5000, 5030)]
FAR_FROM_PEAKS = [(2000, 2030), (3900, 3930), (5700, 5730)]
CONFIG_LINE = (
    "Config: window 60 s, baseline global (median, mean fallback), "
    "min separation 120 s, lead 60 s, tail 15 s"
)


@pytest.fixture(autouse=True)
def isolate_environment(monkeypatch):
    def forbidden_client(*args, **kwargs):
        raise AssertionError("tests must never build the real Gemini client")

    monkeypatch.setattr(judge_module, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setattr(judge_module.genai, "Client", forbidden_client)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)


def clip(start_s, end_s):
    return ReferenceClip(start_s=start_s, end_s=end_s)


def clips(pairs):
    return [clip(start_s, end_s) for start_s, end_s in pairs]


def planted_chat_events():
    events = [ChatEvent(t_s=float(t), message="x") for t in range(0, 6000, 5)]
    for second, count in ((1000, 48), (3000, 36), (5000, 24)):
        events += [ChatEvent(t_s=float(second), message="x")] * count
    return events


def write_chat(tmp_path, name="chat.json"):
    path = tmp_path / name
    content = [
        {"t_s": event.t_s, "message": event.message} for event in planted_chat_events()
    ]
    path.write_text(json.dumps(content), encoding="utf-8")
    return path


def write_reference(tmp_path, pairs, name="reference.json"):
    path = tmp_path / name
    content = [{"start_s": start_s, "end_s": end_s} for start_s, end_s in pairs]
    path.write_text(json.dumps(content), encoding="utf-8")
    return path


def cli_args(tmp_path, pairs=NEAR_PEAKS, **overrides):
    values = {
        "--chat": write_chat(tmp_path),
        "--reference": write_reference(tmp_path, pairs),
        "--k": 3,
        "--trials": TRIALS,
        "--seed": SEED,
    }
    values.update(overrides)
    return [
        part
        for key, value in values.items()
        if value is not None
        for part in (key, str(value))
    ]


def table_rows(lines, title="By moment:"):
    pattern = re.compile(
        r"^\s+(\d+)\s+(\d+)\s+(\d+)/(\d+)\s+(\d+\.\d\d)\s+(\d\.\d{4})$"
    )
    rows = []
    in_table = False
    for line in lines:
        if line.endswith(":") and not line.startswith(" "):
            in_table = line == title
        elif in_table and (match := pattern.match(line)):
            rows.append(match.groups())
    return rows


def test_count_hits_counts_each_clip_once():
    windows = [(0, 100), (50, 150)]

    assert count_hits(windows, clips([(100, 120), (400, 420), (700, 720)])) == 1


def test_count_hits_does_not_double_count_a_clip_matched_by_several_windows():
    windows = [(0, 100), (10, 110), (20, 120)]

    assert count_hits(windows, clips([(100, 120)])) == 1


def test_count_hits_counts_every_clip_a_single_window_reaches():
    assert count_hits([(0, 200)], clips([(10, 20), (150, 160), (900, 910)])) == 2


def test_count_hits_uses_the_sixty_second_tolerance_with_inclusive_edges():
    reference = clips([(160, 200)])

    assert count_hits([(0, 100)], reference) == 1
    assert count_hits([(0, 99)], reference) == 0
    assert count_hits([(260, 300)], reference) == 1
    assert count_hits([(261, 300)], reference) == 0


def test_count_hits_without_windows_or_reference_is_zero():
    assert count_hits([], clips([(10, 20)])) == 0
    assert count_hits([(0, 100)], []) == 0


def test_random_hits_is_deterministic_for_a_seed():
    reference = clips(NEAR_PEAKS)

    first = [
        random_hits(5, POSITIONS, DetectorConfig(), reference, random.Random(7))
        for _ in range(3)
    ]

    assert first[0] == first[1] == first[2]


def test_random_hits_advances_the_generator_between_trials():
    reference = clips([(60, 3000)])
    config = DetectorConfig()
    rng = random.Random(3)

    draws = [random_hits(1, 6000, config, reference, rng) for _ in range(40)]

    assert set(draws) == {0, 1}


def test_random_hits_with_the_same_seed_repeats_the_whole_sequence():
    reference = clips([(60, 3000)])
    config = DetectorConfig()

    def sequence(seed):
        rng = random.Random(seed)
        return [random_hits(2, 6000, config, reference, rng) for _ in range(30)]

    assert sequence(11) == sequence(11)
    assert sequence(11) != sequence(12)


def test_random_hits_draws_starts_without_replacement(monkeypatch):
    config = DetectorConfig(window_s=1, lead_s=0, tail_s=0, min_separation_s=1)
    reference = clips([(0, 1), (1, 2), (2, 3)])
    monkeypatch.setattr(
        harness_module,
        "window_matches",
        lambda start_s, end_s, clip_: start_s == clip_.start_s,
    )

    for seed in range(25):
        hits = random_hits(3, 3, config, reference, random.Random(seed))
        assert hits == 3


def test_random_hits_with_more_windows_than_positions_uses_every_position(
    monkeypatch,
):
    config = DetectorConfig(window_s=1, lead_s=0, tail_s=0, min_separation_s=1)
    reference = clips([(0, 1), (1, 2), (2, 3)])
    monkeypatch.setattr(
        harness_module,
        "window_matches",
        lambda start_s, end_s, clip_: start_s == clip_.start_s,
    )

    assert random_hits(10, 3, config, reference, random.Random(0)) == 3


def test_random_hits_builds_windows_with_the_candidate_geometry():
    reference = clips([(200, 220)])

    short_tail = random_hits(10, 10, DetectorConfig(), reference, random.Random(0))
    long_tail = random_hits(
        10, 10, DetectorConfig(tail_s=100), reference, random.Random(0)
    )

    assert short_tail == 0
    assert long_tail == 1


def test_random_hits_far_from_the_clip_is_zero():
    config = DetectorConfig()
    reference = clips([(5000, 5030)])

    assert random_hits(10, 10, config, reference, random.Random(0)) == 0


class CountingRandom(random.Random):
    def __init__(self, seed):
        super().__init__(seed)
        self.choices = 0

    def choice(self, seq):
        self.choices += 1
        return super().choice(seq)


def all_separated(starts, min_separation_s):
    return all(
        abs(a - b) >= max(min_separation_s, 1)
        for a, b in itertools.combinations(starts, 2)
    )


def test_spaced_random_starts_are_always_at_least_the_separation_apart():
    for seed in range(300):
        starts = spaced_random_starts(8, 1500, 120, random.Random(seed))

        assert len(starts) == 8
        assert all_separated(starts, 120)
        assert all(0 <= start < 1500 for start in starts)


def test_spaced_random_starts_are_deterministic_for_a_seed():
    first = spaced_random_starts(8, 1500, 120, random.Random(5))
    second = spaced_random_starts(8, 1500, 120, random.Random(5))
    other = spaced_random_starts(8, 1500, 120, random.Random(6))

    assert first == second
    assert first != other


def test_spaced_random_starts_terminate_and_place_what_fits_when_there_is_no_room():
    sizes = set()
    for seed in range(200):
        starts = spaced_random_starts(10, 300, 120, random.Random(seed))
        sizes.add(len(starts))
        assert all_separated(starts, 120)

    assert sizes == {2, 3}


def test_spaced_random_starts_place_a_single_window_when_one_position_exists():
    assert spaced_random_starts(5, 1, 120, random.Random(0)) == [0]


def test_spaced_random_starts_with_the_minimum_separation_never_repeat_a_position():
    for seed in range(50):
        starts = spaced_random_starts(4, 6, 1, random.Random(seed))
        assert len(set(starts)) == 4

    assert sorted(spaced_random_starts(10, 5, 1, random.Random(1))) == [0, 1, 2, 3, 4]


def test_spaced_random_starts_without_windows_is_empty():
    assert spaced_random_starts(0, 100, 120, random.Random(0)) == []


def test_spaced_random_starts_reach_the_fallback_when_positions_run_out():
    reached = 0
    for seed in range(100):
        rng = CountingRandom(seed)
        starts = spaced_random_starts(10, 300, 120, rng)
        reached += rng.choices > 0
        assert all_separated(starts, 120)

    assert reached > 0


def test_spaced_random_starts_do_not_use_the_fallback_when_rejection_suffices():
    rng = CountingRandom(0)

    spaced_random_starts(3, 5000, 120, rng)

    assert rng.choices == 0


def test_spaced_random_starts_fallback_alone_respects_the_separation(monkeypatch):
    monkeypatch.setattr(harness_module, "MAX_REJECTIONS", 0)
    sizes = set()
    for seed in range(200):
        rng = CountingRandom(seed)
        starts = spaced_random_starts(10, 300, 120, rng)
        sizes.add(len(starts))
        assert rng.choices == len(starts)
        assert all_separated(starts, 120)

    assert sizes == {2, 3}


def test_spaced_random_starts_fallback_keeps_the_starts_chosen_by_rejection(
    monkeypatch,
):
    monkeypatch.setattr(harness_module, "MAX_REJECTIONS", 1)
    resumed = 0
    for seed in range(300):
        rng = CountingRandom(seed)
        starts = spaced_random_starts(3, 60, 20, rng)
        resumed += rng.choices > 0 and rng.choices < len(starts)
        assert all_separated(starts, 20)
        assert len(set(starts)) == len(starts)

    assert resumed > 0


def test_random_hits_passes_the_config_separation_to_the_spaced_draw(monkeypatch):
    calls = []

    def fake(n_windows, positions, min_separation_s, rng):
        calls.append((n_windows, positions, min_separation_s, rng))
        return [0]

    monkeypatch.setattr(harness_module, "spaced_random_starts", fake)
    rng = random.Random(0)

    random_hits(4, 900, DetectorConfig(min_separation_s=77), clips([(0, 30)]), rng)

    assert calls == [(4, 900, 77, rng)]


def test_random_hits_windows_are_never_closer_than_the_config_separation(
    monkeypatch,
):
    seen = []
    real = harness_module.candidate_window

    def spy(start, config):
        seen.append(start)
        return real(start, config)

    monkeypatch.setattr(harness_module, "candidate_window", spy)
    config = DetectorConfig(min_separation_s=120)

    for seed in range(100):
        seen.clear()
        random_hits(6, 1000, config, clips([(500, 520)]), random.Random(seed))
        assert len(seen) == 6
        assert all_separated(seen, 120)


def test_is_separated_accepts_exactly_the_minimum_separation():
    assert is_separated(120, [0], 120) is True
    assert is_separated(119, [0], 120) is False
    assert is_separated(0, [120], 120) is True
    assert is_separated(1, [120], 120) is False


def test_is_separated_checks_every_chosen_position():
    assert is_separated(500, [0, 200, 400], 120) is False
    assert is_separated(520, [0, 200, 400], 120) is True
    assert is_separated(300, [0, 200, 400], 120) is False


def test_is_separated_with_nothing_chosen_is_true():
    assert is_separated(7, [], 120) is True


def test_is_separated_never_accepts_a_position_already_chosen():
    assert is_separated(5, [5], 1) is False
    assert is_separated(6, [5], 1) is True


def make_result(**overrides):
    values = {
        "k": 20,
        "candidates": 20,
        "hits": 5,
        "random_mean": 1.7,
        "p_value": 0.049,
    }
    values.update(overrides)
    return KResult(**values)


def test_passes_requires_a_p_value_below_five_percent():
    assert passes(make_result(p_value=0.049)) is True
    assert passes(make_result(p_value=0.05)) is False
    assert passes(make_result(p_value=0.4)) is False


def test_passes_requires_at_least_one_candidate():
    assert passes(make_result(candidates=0, p_value=0.001)) is False
    assert passes(make_result(candidates=1, p_value=0.001)) is True


def test_k_result_is_immutable():
    result = make_result()

    with pytest.raises(AttributeError):
        result.hits = 9


def evaluate_planted(pairs):
    return evaluate_k(
        planted_chat_events(), clips(pairs), PEAK_CONFIG, POSITIONS, TRIALS, SEED
    )


def test_evaluate_k_passes_when_the_reference_sits_on_the_peaks():
    result = evaluate_planted(NEAR_PEAKS)

    assert result.k == 3
    assert result.candidates == 3
    assert result.hits == 3
    assert 0 <= result.random_mean < 1
    assert 1 / (TRIALS + 1) <= result.p_value < 0.05
    assert passes(result) is True


def test_evaluate_k_fails_when_the_reference_is_far_from_the_peaks():
    result = evaluate_planted(FAR_FROM_PEAKS)

    assert result.k == 3
    assert result.candidates == 3
    assert result.hits == 0
    assert result.p_value == 1.0
    assert passes(result) is False


def test_evaluate_k_is_deterministic_for_a_seed():
    assert evaluate_planted(NEAR_PEAKS) == evaluate_planted(NEAR_PEAKS)


def test_evaluate_k_p_value_never_reaches_zero():
    result = evaluate_planted(NEAR_PEAKS)

    assert result.p_value >= 1 / (TRIALS + 1)


def test_evaluate_k_reports_the_k_of_its_config():
    result = evaluate_k(
        planted_chat_events(),
        clips(NEAR_PEAKS),
        DetectorConfig(top_k=5),
        POSITIONS,
        TRIALS,
        SEED,
    )

    assert result.k == 5
    assert result.candidates == 5
    assert result.hits == 3


def test_evaluate_k_uses_window_matches_from_the_evaluation_module():
    assert harness_module.window_matches is evaluate_module.window_matches


def test_evaluate_k_follows_a_changed_matching_criterion(monkeypatch):
    baseline = evaluate_planted(NEAR_PEAKS)
    monkeypatch.setattr(harness_module, "window_matches", lambda *args: False)

    changed = evaluate_planted(NEAR_PEAKS)

    assert baseline.hits == 3
    assert changed.hits == 0
    assert changed.random_mean == 0.0
    assert changed.p_value == 1.0


def test_count_hits_follows_a_changed_matching_criterion(monkeypatch):
    reference = clips([(100, 120), (900, 920)])
    monkeypatch.setattr(harness_module, "window_matches", lambda *args: True)

    assert count_hits([(5000, 5100)], reference) == 2


def noisy_chat_events(seed, duration_s=4000):
    rng = random.Random(seed)
    return [
        ChatEvent(t_s=float(second), message="x")
        for second in range(duration_s)
        for _ in range(rng.choice((0, 0, 1, 1, 2)))
    ]


def independent_reference(seed, duration_s=4000, count=20):
    rng = random.Random(seed)
    starts = [rng.randrange(duration_s) for _ in range(count)]
    return [clip(start, start + 30) for start in starts]


def test_evaluate_k_random_baseline_is_calibrated_on_a_chat_without_signal():
    config = DetectorConfig(top_k=20)
    differences = []
    p_values = []
    for seed in range(40):
        events = noisy_chat_events(seed)
        positions = len(window_sums(count_messages_per_second(events), config.window_s))
        result = evaluate_k(
            events, independent_reference(1000 + seed), config, positions, 100, 7
        )
        differences.append(result.hits - result.random_mean)
        p_values.append(result.p_value)

    assert abs(statistics.fmean(differences)) < 1.5
    assert sum(p < 0.05 for p in p_values) <= 6


def test_evaluate_k_draws_as_many_random_windows_as_there_are_candidates(
    monkeypatch,
):
    drawn = []
    real = harness_module.random_hits

    def spy(n_windows, positions, config, reference, rng):
        drawn.append(n_windows)
        return real(n_windows, positions, config, reference, rng)

    monkeypatch.setattr(harness_module, "random_hits", spy)
    events = [ChatEvent(t_s=100.0, message="x")] * 120

    result = evaluate_k(events, clips(NEAR_PEAKS), DetectorConfig(top_k=5), 500, 12, 1)

    assert result.candidates == 1
    assert drawn == [1] * 12


def test_evaluate_k_random_mean_is_the_arithmetic_mean_of_the_trials(monkeypatch):
    outcomes = iter([0, 0, 0, 4])
    monkeypatch.setattr(harness_module, "random_hits", lambda *args: next(outcomes))

    result = evaluate_k(
        planted_chat_events(), clips(NEAR_PEAKS), PEAK_CONFIG, POSITIONS, 4, SEED
    )

    assert result.random_mean == 1.0
    assert result.hits == 3
    assert result.p_value == pytest.approx(2 / 5)


def run_to_lines(tmp_path, pairs, config=PEAK_CONFIG, trials=TRIALS, seed=SEED):
    stream = io.StringIO()
    ok = run(
        write_chat(tmp_path),
        write_reference(tmp_path, pairs),
        config,
        trials,
        seed,
        stream,
    )
    return ok, stream.getvalue().splitlines()


def test_run_prints_the_header_lines(tmp_path):
    _, lines = run_to_lines(tmp_path, NEAR_PEAKS)

    assert lines[:7] == [
        "Chat: 1308 messages, 5937 window positions",
        "Reference clips: 3 (tolerance +/-60 s)",
        "Reference moments: 3 (clips less than 60 s apart merged)",
        CONFIG_LINE,
        "Random baseline: 200 trials, seed 1",
        "By clip:",
        "    K  candidates  hits  random mean  p-value",
    ]
    assert "By moment:" in lines


def test_run_prints_one_row_per_reported_k_plus_the_configured_k(tmp_path):
    _, lines = run_to_lines(tmp_path, NEAR_PEAKS)

    rows = table_rows(lines)

    assert [row[0] for row in rows] == ["3", "5", "10", "20", "40"]
    assert [row[1] for row in rows] == ["3", "5", "10", "20", "40"]
    assert rows[0][2:4] == ("3", "3")


def test_run_does_not_repeat_the_configured_k_when_it_is_already_reported(tmp_path):
    _, lines = run_to_lines(tmp_path, NEAR_PEAKS, config=DetectorConfig(top_k=10))

    assert [row[0] for row in table_rows(lines)] == ["5", "10", "20", "40"]


def test_run_row_for_the_configured_k_matches_evaluate_k(tmp_path):
    _, lines = run_to_lines(tmp_path, NEAR_PEAKS)

    result = evaluate_planted(NEAR_PEAKS)

    expected = (
        "3",
        str(result.candidates),
        str(result.hits),
        "3",
        f"{result.random_mean:.2f}",
        f"{result.p_value:.4f}",
    )
    assert table_rows(lines)[0] == expected
    assert table_rows(lines, "By clip:")[0] == expected


def test_run_returns_true_and_prints_a_pass_verdict_for_a_reference_on_the_peaks(
    tmp_path,
):
    ok, lines = run_to_lines(tmp_path, NEAR_PEAKS)

    result = evaluate_planted(NEAR_PEAKS)
    assert ok is True
    assert lines[-1] == (
        "Verdict (hits@3 above random with p<0.05, counted by moment, never silent): PASS - "
        f"hits 3/3, random mean {result.random_mean:.2f}, "
        f"p={result.p_value:.4f}, candidates 3"
    )


def test_run_returns_false_and_prints_a_fail_verdict_far_from_the_peaks(tmp_path):
    ok, lines = run_to_lines(tmp_path, FAR_FROM_PEAKS)

    result = evaluate_planted(FAR_FROM_PEAKS)
    assert ok is False
    assert lines[-1] == (
        "Verdict (hits@3 above random with p<0.05, counted by moment, never silent): FAIL - "
        f"hits 0/3, random mean {result.random_mean:.2f}, "
        f"p=1.0000, candidates 3"
    )


def test_run_verdict_is_the_last_line_and_names_the_configured_k(tmp_path):
    _, lines = run_to_lines(tmp_path, NEAR_PEAKS, config=DetectorConfig(top_k=20))

    assert lines[-1].startswith("Verdict (hits@20 above random with p<0.05")
    assert sum(line.startswith("Verdict") for line in lines) == 1


DUPLICATED_FIRST_PEAK = [(1000, 1030), (1010, 1040), (1040, 1070), (3000, 3030)]


def test_run_counts_a_repeated_moment_once_in_the_moment_table(tmp_path):
    _, lines = run_to_lines(tmp_path, DUPLICATED_FIRST_PEAK)

    assert lines[2] == "Reference moments: 2 (clips less than 60 s apart merged)"
    assert table_rows(lines, "By clip:")[0][2:4] == ("4", "4")
    assert table_rows(lines)[0][2:4] == ("2", "2")


def test_run_by_clip_table_matches_evaluate_k_on_the_raw_reference(tmp_path):
    _, lines = run_to_lines(tmp_path, DUPLICATED_FIRST_PEAK)

    result = evaluate_k(
        planted_chat_events(),
        clips(DUPLICATED_FIRST_PEAK),
        PEAK_CONFIG,
        POSITIONS,
        TRIALS,
        SEED,
    )

    assert table_rows(lines, "By clip:")[0] == (
        "3",
        str(result.candidates),
        str(result.hits),
        "4",
        f"{result.random_mean:.2f}",
        f"{result.p_value:.4f}",
    )


def test_run_by_moment_table_matches_evaluate_k_on_the_fused_reference(tmp_path):
    _, lines = run_to_lines(tmp_path, DUPLICATED_FIRST_PEAK)

    result = evaluate_k(
        planted_chat_events(),
        merge_reference(clips(DUPLICATED_FIRST_PEAK)),
        PEAK_CONFIG,
        POSITIONS,
        TRIALS,
        SEED,
    )

    assert table_rows(lines)[0] == (
        "3",
        str(result.candidates),
        str(result.hits),
        "2",
        f"{result.random_mean:.2f}",
        f"{result.p_value:.4f}",
    )


def test_run_verdict_counts_by_moment_not_by_clip(tmp_path):
    _, lines = run_to_lines(tmp_path, DUPLICATED_FIRST_PEAK)

    assert "counted by moment" in lines[-1]
    assert "hits 2/2" in lines[-1]


def test_run_without_repeated_clips_gives_the_same_count_in_both_tables(tmp_path):
    _, lines = run_to_lines(tmp_path, NEAR_PEAKS)

    assert table_rows(lines) == table_rows(lines, "By clip:")


def storm_rows(lines):
    pattern = re.compile(r"^\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)%\s+(.+)$")
    start = next(i for i, line in enumerate(lines) if line.startswith("Storms ("))
    return [m.groups() for line in lines[start + 2 :] if (m := pattern.match(line))]


def test_run_prints_the_storm_section_between_the_tables_and_the_verdict(tmp_path):
    _, lines = run_to_lines(tmp_path, NEAR_PEAKS)

    title = next(i for i, line in enumerate(lines) if line.startswith("Storms ("))

    assert lines.index("By moment:") < title < len(lines) - 1
    assert lines[title] == (
        "Storms (peak windows with at most 35% distinct messages; flagged "
        "peaks up to 300 s apart form one storm):"
    )
    assert lines[title + 1] == "    K  flagged  largest storm  share  dominant message"


def test_run_prints_one_storm_row_per_k(tmp_path):
    _, lines = run_to_lines(tmp_path, NEAR_PEAKS)

    assert [row[0] for row in storm_rows(lines)] == ["3", "5", "10", "20", "40"]


def test_run_storm_rows_measure_the_peaks_of_each_k(tmp_path):
    _, lines = run_to_lines(tmp_path, NEAR_PEAKS)

    first = storm_rows(lines)[0]

    assert first == ("3", "3", "1", "33", "x")


def test_run_does_not_repeat_the_configured_k_in_the_storm_section(tmp_path):
    _, lines = run_to_lines(tmp_path, NEAR_PEAKS, config=DetectorConfig(top_k=10))

    assert [row[0] for row in storm_rows(lines)] == ["5", "10", "20", "40"]


def test_run_storm_section_shows_a_dash_when_there_is_no_storm(tmp_path, monkeypatch):
    varied = [
        ChatEvent(t_s=float(t), message=f"m{t}-{i}")
        for t in range(0, 6000, 5)
        for i in range(1)
    ]
    for second, count in ((1000, 48), (3000, 36), (5000, 24)):
        varied += [
            ChatEvent(t_s=float(second), message=f"u{second}-{i}") for i in range(count)
        ]
    chat = tmp_path / "varied.json"
    chat.write_text(
        json.dumps([{"t_s": e.t_s, "message": e.message} for e in varied]),
        encoding="utf-8",
    )
    stream = io.StringIO()

    run(chat, write_reference(tmp_path, NEAR_PEAKS), PEAK_CONFIG, TRIALS, SEED, stream)

    first = storm_rows(stream.getvalue().splitlines())[0]
    assert first == ("3", "0", "0", "0", "-")


def test_run_writes_only_to_the_given_stream(tmp_path, capsys):
    run_to_lines(tmp_path, NEAR_PEAKS)

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_run_prints_to_stdout_by_default(tmp_path, capsys):
    run(
        write_chat(tmp_path),
        write_reference(tmp_path, NEAR_PEAKS),
        PEAK_CONFIG,
        TRIALS,
        SEED,
    )

    captured = capsys.readouterr()
    assert captured.out.splitlines()[0].startswith("Chat: 1308 messages")
    assert captured.err == ""


def test_run_is_deterministic_for_a_seed(tmp_path):
    first = run_to_lines(tmp_path, NEAR_PEAKS)
    second = run_to_lines(tmp_path, NEAR_PEAKS)

    assert first == second


def test_run_uses_the_shared_matching_criterion(tmp_path, monkeypatch):
    monkeypatch.setattr(harness_module, "window_matches", lambda *args: True)

    ok, lines = run_to_lines(tmp_path, FAR_FROM_PEAKS)

    assert ok is False
    assert "hits 3/3" in lines[-1]


def test_run_reports_the_window_size_of_the_config(tmp_path):
    _, lines = run_to_lines(
        tmp_path, NEAR_PEAKS, config=DetectorConfig(window_s=30, top_k=3)
    )

    assert lines[0] == "Chat: 1308 messages, 5967 window positions"
    assert lines[3].startswith("Config: window 30 s, baseline global (median")


def test_main_exits_zero_on_pass(tmp_path, capsys):
    code = main(cli_args(tmp_path))

    captured = capsys.readouterr()
    assert code == EXIT_OK == 0
    assert "PASS" in captured.out.splitlines()[-1]
    assert captured.err == ""


def test_main_exits_zero_on_fail_too(tmp_path, capsys):
    code = main(cli_args(tmp_path, pairs=FAR_FROM_PEAKS))

    captured = capsys.readouterr()
    assert code == EXIT_OK == 0
    assert "FAIL" in captured.out.splitlines()[-1]
    assert captured.err == ""


def test_main_defaults_to_k_twenty_and_window_sixty(tmp_path, capsys):
    code = main(cli_args(tmp_path, **{"--k": None, "--trials": 20}))

    lines = capsys.readouterr().out.splitlines()
    assert code == EXIT_OK
    assert lines[3].startswith("Config: window 60 s")
    assert lines[4] == "Random baseline: 20 trials, seed 1"
    assert lines[-1].startswith("Verdict (hits@20 ")
    assert [row[0] for row in table_rows(lines)] == ["5", "10", "20", "40"]


def test_main_passes_the_window_size_to_the_detector(tmp_path, capsys):
    code = main(cli_args(tmp_path, **{"--window-s": 30}))

    lines = capsys.readouterr().out.splitlines()
    assert code == EXIT_OK
    assert lines[0] == "Chat: 1308 messages, 5967 window positions"


def test_main_seed_defaults_to_zero(tmp_path, capsys):
    main(cli_args(tmp_path, **{"--seed": None}))

    assert "seed 0" in capsys.readouterr().out


def test_main_missing_chat_file_exits_one_with_an_error(tmp_path, capsys):
    code = main(cli_args(tmp_path, **{"--chat": tmp_path / "nope.json"}))

    captured = capsys.readouterr()
    assert code == EXIT_FATAL == 1
    assert captured.err.startswith("error: ")
    assert "nope.json" in captured.err
    assert "file does not exist" in captured.err
    assert captured.out == ""


def test_main_invalid_reference_exits_one_with_an_error(tmp_path, capsys):
    reference = tmp_path / "bad.json"
    reference.write_text(json.dumps([{"start_s": 5, "end_s": 5}]), encoding="utf-8")

    code = main(cli_args(tmp_path, **{"--reference": reference}))

    captured = capsys.readouterr()
    assert code == EXIT_FATAL
    assert captured.err.startswith("error: ")
    assert "end_s must be greater than start_s" in captured.err
    assert captured.out == ""


def test_main_undecodable_input_exits_one_instead_of_crashing(tmp_path, capsys):
    chat = tmp_path / "binary.json"
    chat.write_bytes(b"\xff\xfe\x00 not utf-8 \xff")

    code = main(cli_args(tmp_path, **{"--chat": chat}))

    captured = capsys.readouterr()
    assert code == EXIT_FATAL
    assert captured.err.startswith("error: ")
    assert "Traceback" not in captured.err


def test_main_chat_without_activity_exits_one(tmp_path, capsys):
    chat = tmp_path / "empty_chat.json"
    chat.write_text("[]", encoding="utf-8")

    code = main(cli_args(tmp_path, **{"--chat": chat}))

    captured = capsys.readouterr()
    assert code == EXIT_FATAL
    assert captured.err == "error: chat sin actividad suficiente\n"


def test_main_empty_reference_exits_one_with_an_explicit_error(tmp_path, capsys):
    reference = tmp_path / "empty_reference.json"
    reference.write_text("[]", encoding="utf-8")

    code = main(cli_args(tmp_path, **{"--reference": reference}))

    captured = capsys.readouterr()
    assert code == EXIT_FATAL
    assert captured.err == "error: empty_reference.json: reference has no clips\n"
    assert captured.out == ""


@pytest.mark.parametrize("last_s", [172801, 1e9, 1e15])
def test_main_chat_longer_than_48_hours_exits_one_naming_the_value(
    tmp_path, capsys, last_s
):
    chat = tmp_path / "huge_chat.json"
    chat.write_text(
        json.dumps([{"t_s": 5, "message": "x"}, {"t_s": last_s, "message": "y"}]),
        encoding="utf-8",
    )

    code = main(cli_args(tmp_path, **{"--chat": chat}))

    captured = capsys.readouterr()
    assert code == EXIT_FATAL
    assert captured.err.startswith("error: chat spans ")
    assert str(int(last_s)) in captured.err
    assert "172800" in captured.err
    assert "Traceback" not in captured.err
    assert captured.out == ""


def test_main_sparse_chat_below_the_mean_floor_exits_one(tmp_path, capsys):
    chat = tmp_path / "sparse_chat.json"
    chat.write_text(
        json.dumps([{"t_s": 0, "message": "x"}, {"t_s": 3000, "message": "y"}]),
        encoding="utf-8",
    )

    code = main(cli_args(tmp_path, **{"--chat": chat}))

    captured = capsys.readouterr()
    assert code == EXIT_FATAL
    assert captured.err == "error: chat sin actividad suficiente\n"


@pytest.mark.parametrize("trials", [0, -3, 1, 19])
def test_main_rejects_fewer_than_twenty_trials_with_code_two(tmp_path, capsys, trials):
    with pytest.raises(SystemExit) as exit_info:
        main(cli_args(tmp_path, **{"--trials": trials}))

    assert exit_info.value.code == 2
    assert "--trials must be at least 20" in capsys.readouterr().err


def test_min_trials_is_the_smallest_count_that_allows_a_pass():
    assert 1 / (MIN_TRIALS + 1) < SIGNIFICANCE <= 1 / MIN_TRIALS


def test_main_accepts_exactly_twenty_trials(tmp_path):
    assert main(cli_args(tmp_path, **{"--trials": 20})) == EXIT_OK


@pytest.mark.parametrize(
    "overrides", [{"--window-s": 0}, {"--window-s": -60}, {"--k": 0}, {"--k": -1}]
)
def test_main_rejects_an_invalid_detector_config_with_code_two(
    tmp_path, capsys, overrides
):
    with pytest.raises(SystemExit) as exit_info:
        main(cli_args(tmp_path, **overrides))

    captured = capsys.readouterr()
    assert exit_info.value.code == 2
    assert "must be an integer >= 1" in captured.err
    assert captured.out == ""


@pytest.mark.parametrize("missing", ["--chat", "--reference"])
def test_main_missing_required_argument_exits_with_code_two(tmp_path, capsys, missing):
    with pytest.raises(SystemExit) as exit_info:
        main(cli_args(tmp_path, **{missing: None}))

    assert exit_info.value.code == 2
    assert missing in capsys.readouterr().err


def test_main_non_numeric_option_exits_with_code_two(tmp_path, capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(cli_args(tmp_path, **{"--seed": "abc"}))

    assert exit_info.value.code == 2


def test_main_keyboard_interrupt_returns_130(tmp_path, capsys, monkeypatch):
    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(harness_module, "run", interrupted)

    code = main(cli_args(tmp_path))

    captured = capsys.readouterr()
    assert code == EXIT_INTERRUPTED == 130
    assert captured.err == "error: interrupted\n"
    assert "Traceback" not in captured.err


def test_main_os_error_exits_one(tmp_path, capsys, monkeypatch):
    def failing(*args, **kwargs):
        raise OSError("disk unavailable")

    monkeypatch.setattr(harness_module, "run", failing)

    code = main(cli_args(tmp_path))

    assert code == EXIT_FATAL
    assert capsys.readouterr().err == "error: disk unavailable\n"


def test_main_needs_no_api_key_and_never_builds_the_judge_client(tmp_path, capsys):
    code = main(cli_args(tmp_path))

    assert code == EXIT_OK
    assert "GEMINI_API_KEY" not in capsys.readouterr().err


def test_the_harness_offers_no_upload_or_judge_option():
    parser = harness_module._parser()

    options = {option for action in parser._actions for option in action.option_strings}

    assert options == {
        "-h",
        "--help",
        "--chat",
        "--reference",
        "--window-s",
        "--k",
        "--trials",
        "--seed",
    }
