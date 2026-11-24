import pytest

import src.judge as judge_module
from src.evaluate import (
    MOMENT_GAP_S,
    TOLERANCE_S,
    ClipResult,
    EvaluationReport,
    evaluate,
    format_report,
    merge_reference,
    window_matches,
)
from src.models import Breakdown, Chat, Moment, ReferenceClip
from src.timeparse import seconds_to_hhmmss


@pytest.fixture(autouse=True)
def isolate_environment(monkeypatch):
    def forbidden_client(*args, **kwargs):
        raise AssertionError("tests must never build the real Gemini client")

    monkeypatch.setattr(judge_module, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setattr(judge_module.genai, "Client", forbidden_client)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)


def make_moment(start_s, end_s):
    breakdown = Breakdown(reaccion_chat=20, contexto=10, novedad=10, gancho=10)
    return Moment(
        inicio=seconds_to_hhmmss(start_s),
        fin=seconds_to_hhmmss(end_s),
        puntuacion=breakdown.total,
        desglose=breakdown,
        categoria="jugada",
        gancho="Mira esto",
        chat=Chat(msg_min=60.0, multiplicador=3.0),
    )


def make_clip(start_s=1000, end_s=1030):
    return ReferenceClip(start_s=start_s, end_s=end_s)


def detected_flags(moments, reference):
    return [result.detected for result in evaluate(moments, reference).clips]


def test_tolerance_is_sixty_seconds():
    assert TOLERANCE_S == 60


def test_moment_overlapping_the_clip_is_a_hit():
    assert detected_flags([make_moment(990, 1020)], [make_clip()]) == [True]


def test_moment_inside_the_clip_is_a_hit():
    assert detected_flags([make_moment(1010, 1020)], [make_clip()]) == [True]


def test_moment_containing_the_clip_is_a_hit():
    assert detected_flags([make_moment(900, 1200)], [make_clip()]) == [True]


def test_moment_identical_to_the_clip_is_a_hit():
    assert detected_flags([make_moment(1000, 1030)], [make_clip()]) == [True]


def test_moment_within_tolerance_before_the_clip_is_a_hit():
    assert detected_flags([make_moment(920, 950)], [make_clip()]) == [True]


def test_moment_within_tolerance_after_the_clip_is_a_hit():
    assert detected_flags([make_moment(1050, 1080)], [make_clip()]) == [True]


def test_moment_ending_exactly_sixty_seconds_before_the_clip_is_a_hit():
    assert detected_flags([make_moment(900, 940)], [make_clip()]) == [True]


def test_moment_ending_sixty_one_seconds_before_the_clip_is_a_miss():
    assert detected_flags([make_moment(900, 939)], [make_clip()]) == [False]


def test_moment_starting_exactly_sixty_seconds_after_the_clip_is_a_hit():
    assert detected_flags([make_moment(1090, 1130)], [make_clip()]) == [True]


def test_moment_starting_sixty_one_seconds_after_the_clip_is_a_miss():
    assert detected_flags([make_moment(1091, 1130)], [make_clip()]) == [False]


def test_far_away_moment_is_a_miss():
    assert detected_flags([make_moment(3000, 3040)], [make_clip()]) == [False]


def test_fractional_clip_edges_use_the_exact_value():
    clip = make_clip(1000, 1030.5)

    assert detected_flags([make_moment(1090, 1100)], [clip]) == [True]
    assert detected_flags([make_moment(1091, 1100)], [clip]) == [False]


def test_any_moment_is_enough_to_detect_a_clip():
    moments = [make_moment(100, 140), make_moment(3000, 3040), make_moment(1010, 1040)]

    assert detected_flags(moments, [make_clip()]) == [True]


def test_one_moment_can_detect_several_clips():
    reference = [make_clip(1000, 1030), make_clip(1100, 1130)]

    assert detected_flags([make_moment(1040, 1090)], reference) == [True, True]


def test_no_moments_detect_nothing():
    report = evaluate([], [make_clip(), make_clip(2000, 2030)])

    assert report.total == 2
    assert report.detected == 0
    assert [result.detected for result in report.clips] == [False, False]


def test_empty_reference_has_total_zero():
    report = evaluate([make_moment(10, 50)], [])

    assert report == EvaluationReport(total=0, detected=0, clips=[])


def test_order_of_the_reference_clips_is_preserved():
    reference = [
        make_clip(3000, 3030),
        make_clip(100, 130),
        make_clip(2000, 2030),
    ]

    report = evaluate([make_moment(120, 160), make_moment(2010, 2040)], reference)

    assert [result.clip for result in report.clips] == reference
    assert [result.detected for result in report.clips] == [False, True, True]
    assert (report.total, report.detected) == (3, 2)


def test_report_accepts_any_sequence_type():
    report = evaluate((make_moment(1000, 1030),), (make_clip(),))

    assert (report.total, report.detected) == (1, 1)


def test_clip_result_and_report_reject_unknown_fields():
    with pytest.raises(ValueError):
        ClipResult(clip=make_clip(), detected=True, extra=1)
    with pytest.raises(ValueError):
        EvaluationReport(total=0, detected=0, clips=[], extra=1)


def test_format_report_exact_lines():
    reference = [
        make_clip(610, 640),
        make_clip(2010, 2050),
        make_clip(3000, 3030),
    ]
    report = evaluate([make_moment(600, 650), make_moment(2010, 2050)], reference)

    assert format_report(report) == [
        "Evaluation: 2/3 reference clips detected (tolerance +/-60 s)",
        "  - 00:10:10-00:10:40: detected",
        "  - 00:33:30-00:34:10: detected",
        "  - 00:50:00-00:50:30: missed",
    ]


def test_format_report_with_an_empty_reference():
    assert format_report(evaluate([], [])) == [
        "Evaluation: 0/0 reference clips detected (tolerance +/-60 s)"
    ]


def test_format_report_with_hours_and_fractional_seconds():
    report = evaluate([], [ReferenceClip(start_s=5025.9, end_s=5100.2)])

    assert format_report(report) == [
        "Evaluation: 0/1 reference clips detected (tolerance +/-60 s)",
        "  - 01:23:45-01:25:00: missed",
    ]


@pytest.mark.parametrize(
    ("start_s", "end_s", "expected"),
    [
        (1010, 1020, True),
        (900, 1200, True),
        (1000, 1030, True),
        (900, 940, True),
        (900, 939, False),
        (900, 939.9, False),
        (1090, 1130, True),
        (1091, 1130, False),
        (1090.1, 1130, False),
        (3000, 3040, False),
        (0, 10, False),
    ],
)
def test_window_matches_uses_a_sixty_second_tolerance_with_inclusive_edges(
    start_s, end_s, expected
):
    assert window_matches(start_s, end_s, make_clip()) is expected


def test_window_matches_accepts_floats_and_the_exact_tolerance_edges():
    clip = make_clip(1000.5, 1030.5)

    assert window_matches(800.0, 940.5, clip) is True
    assert window_matches(800.0, 940.4, clip) is False
    assert window_matches(1090.5, 1200.0, clip) is True
    assert window_matches(1090.6, 1200.0, clip) is False


@pytest.mark.parametrize(
    ("start_s", "end_s"),
    [(990, 1020), (900, 940), (900, 939), (1090, 1130), (1091, 1130), (3000, 3040)],
)
def test_evaluate_agrees_with_window_matches(start_s, end_s):
    clip = make_clip()

    detected = detected_flags([make_moment(start_s, end_s)], [clip])

    assert detected == [window_matches(start_s, end_s, clip)]


def test_evaluate_routes_the_criterion_through_window_matches(monkeypatch):
    calls = []

    def always_true(start_s, end_s, clip):
        calls.append((start_s, end_s, clip))
        return True

    monkeypatch.setattr("src.evaluate.window_matches", always_true)

    detected = detected_flags([make_moment(3000, 3040)], [make_clip()])

    assert detected == [True]
    assert calls == [(3000, 3040, make_clip())]


def merged(pairs):
    return [
        (clip.start_s, clip.end_s)
        for clip in merge_reference([make_clip(s, e) for s, e in pairs])
    ]


def test_moment_gap_is_sixty_seconds():
    assert MOMENT_GAP_S == 60


def test_merge_reference_keeps_clips_that_are_far_apart():
    assert merged([(100, 130), (500, 530)]) == [(100, 130), (500, 530)]


def test_merge_reference_fuses_overlapping_clips():
    assert merged([(100, 130), (120, 160)]) == [(100, 160)]


def test_merge_reference_fuses_a_clip_contained_in_another():
    assert merged([(100, 300), (150, 160)]) == [(100, 300)]


def test_merge_reference_fuses_clips_less_than_sixty_seconds_apart():
    assert merged([(100, 130), (189, 220)]) == [(100, 220)]


def test_merge_reference_keeps_clips_exactly_sixty_seconds_apart():
    assert merged([(100, 130), (190, 220)]) == [(100, 130), (190, 220)]


def test_merge_reference_chains_fusions_through_a_middle_clip():
    assert merged([(100, 130), (150, 180), (200, 230)]) == [(100, 230)]


def test_merge_reference_is_independent_of_the_input_order():
    pairs = [(500, 530), (100, 130), (120, 160)]

    assert merged(pairs) == merged(list(reversed(pairs))) == [(100, 160), (500, 530)]


def test_merge_reference_of_nothing_is_nothing():
    assert merge_reference([]) == []


def test_merge_reference_returns_reference_clips_and_leaves_the_input_alone():
    reference = [make_clip(120, 160), make_clip(100, 130)]

    result = merge_reference(reference)

    assert all(isinstance(clip, ReferenceClip) for clip in result)
    assert [(c.start_s, c.end_s) for c in reference] == [(120, 160), (100, 130)]


def test_merge_reference_collapses_the_djmariio_triplet_into_one_moment():
    triplet = [(4785, 4815), (4781, 4796), (4815, 4845), (8874, 8929)]

    assert merged(triplet) == [(4781, 4845), (8874, 8929)]


def test_fusing_the_reference_never_changes_which_windows_hit():
    pairs = [(100, 130), (189, 220), (900, 930)]
    reference = [make_clip(s, e) for s, e in pairs]
    fused = merge_reference(reference)

    for start in range(0, 1100, 7):
        window = (start, start + 20)
        assert any(window_matches(*window, c) for c in reference) == any(
            window_matches(*window, c) for c in fused
        )
