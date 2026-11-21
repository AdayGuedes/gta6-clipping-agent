import io
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from google.genai import types

import src.judge as judge_module
import src.main as main_module
from src.evaluate import window_matches
from src.judge import MAX_MOMENTS, GeminiJudge, JudgeError, Judgment
from src.loaders import LoadError, load_chat, load_reference
from src.main import EXIT_FATAL, EXIT_OK, PENDING_REVIEW, ReportsUsage, main, run
from src.models import Moment
from src.peaks import InsufficientChatError, generate_candidates
from src.timeparse import seconds_to_hhmmss

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "examples" / "demo"
TRANSCRIPT = DEMO / "transcript.json"
CHAT = DEMO / "chat.json"
REFERENCE = DEMO / "reference.json"

HOOK_A = "Mira esto, qué locura"
HOOK_B = "¡Qué barbaridad, el coche vuela por España!"
HOOK_C = "Nadie esperaba esta caída"
HOOK_QUIET = "Un minuto tranquilo pero con tema"
HOOK_FILLER = "Relleno sin interés"

PLANTED_STARTS = (540.0, 1978.0, 4139.0)
QUIET_START = 3005.0
FILLER_STARTS = (
    5.0,
    305.0,
    660.0,
    905.0,
    1205.0,
    1505.0,
    1805.0,
    2105.0,
    2405.0,
    2705.0,
    3005.0,
    3305.0,
    3605.0,
    3905.0,
    4259.0,
    4505.0,
    4805.0,
)
DEMO_STARTS = (*PLANTED_STARTS, *FILLER_STARTS)
CANDIDATE_LENGTH_S = 135.0

SPEC_MOMENT_KEYS = {
    "inicio",
    "fin",
    "puntuacion",
    "desglose",
    "categoria",
    "gancho",
    "chat",
}
SPEC_BREAKDOWN_KEYS = {"reaccion_chat", "contexto", "novedad", "gancho"}
SPEC_CHAT_KEYS = {"msg_min", "multiplicador"}

EVALUATION_LINES = [
    "Evaluation: 3/3 reference clips detected (tolerance +/-60 s)",
    "  - 00:10:10-00:10:40: detected",
    "  - 00:33:30-00:34:10: detected",
    "  - 00:50:00-00:50:30: detected",
]


@pytest.fixture(autouse=True)
def isolate_environment(monkeypatch):
    def forbidden_client(*args, **kwargs):
        raise AssertionError("tests must never build the real Gemini client")

    def forbidden_sleep(seconds):
        raise AssertionError("tests must never sleep for real")

    monkeypatch.setattr(judge_module, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setattr(judge_module.genai, "Client", forbidden_client)
    monkeypatch.setattr(judge_module.time, "sleep", forbidden_sleep)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)


def make_judgment(start_s, end_s, hook, context, novelty, hook_score, **overrides):
    values = {
        "start_s": start_s,
        "end_s": end_s,
        "category": "jugada",
        "hook": hook,
        "context_score": context,
        "novelty_score": novelty,
        "hook_score": hook_score,
    }
    values.update(overrides)
    return Judgment(**values)


def planted_outcomes():
    return {
        540.0: [make_judgment(600, 650, HOOK_A, 10, 10, 5)],
        1978.0: [
            make_judgment(2010, 2050, HOOK_B, 22, 18, 15, category="bug gracioso")
        ],
        4139.0: [make_judgment(4200, 4240, HOOK_C, 15, 10, 10)],
    }


def demo_outcomes():
    outcomes = planted_outcomes()
    outcomes[QUIET_START] = [make_judgment(3010, 3050, HOOK_QUIET, 8, 5, 5)]
    return outcomes


def filler_outcome(candidate):
    return make_judgment(
        candidate.start_s + 10, candidate.start_s + 50, HOOK_FILLER, 2, 2, 1
    )


def failing_default(message="down"):
    return lambda candidate: JudgeError(message)


class FakeJudge:
    def __init__(self, outcomes, default=filler_outcome):
        self._outcomes = {key: list(values) for key, values in outcomes.items()}
        self._default = default
        self.requests = []

    def judge(self, candidate, segments):
        self.requests.append(candidate)
        if candidate.start_s in self._outcomes:
            outcome = self._outcomes[candidate.start_s].pop(0)
        else:
            outcome = self._default(candidate)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class UsageJudge(FakeJudge):
    def __init__(self, outcomes, default=filler_outcome):
        super().__init__(outcomes, default)
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0

    def judge(self, candidate, segments):
        self.calls += 1
        self.input_tokens += 100
        self.output_tokens += 25
        return super().judge(candidate, segments)


def run_demo(tmp_path, judge, reference=None):
    out_path = tmp_path / "resultados.json"
    stream = io.StringIO()
    moments = run(TRANSCRIPT, CHAT, out_path, judge, reference, stream)
    return moments, out_path, stream.getvalue().splitlines()


def read_output(out_path):
    return json.loads(out_path.read_text(encoding="utf-8"))


def write_json(tmp_path, name, content):
    path = tmp_path / name
    path.write_text(json.dumps(content), encoding="utf-8")
    return path


# run: output file


def test_output_holds_the_top_five_moments_sorted_by_score(tmp_path):
    _, out_path, _ = run_demo(tmp_path, FakeJudge(demo_outcomes()))

    assert read_output(out_path) == [
        {
            "inicio": "00:33:30",
            "fin": "00:34:10",
            "puntuacion": 83,
            "desglose": {
                "reaccion_chat": 28,
                "contexto": 22,
                "novedad": 18,
                "gancho": 15,
            },
            "categoria": "bug gracioso",
            "gancho": HOOK_B,
            "chat": {"msg_min": 48.0, "multiplicador": 4.0},
        },
        {
            "inicio": "01:10:00",
            "fin": "01:10:40",
            "puntuacion": 56,
            "desglose": {
                "reaccion_chat": 21,
                "contexto": 15,
                "novedad": 10,
                "gancho": 10,
            },
            "categoria": "jugada",
            "gancho": HOOK_C,
            "chat": {"msg_min": 30.0, "multiplicador": 2.5},
        },
        {
            "inicio": "00:10:00",
            "fin": "00:10:50",
            "puntuacion": 54,
            "desglose": {
                "reaccion_chat": 29,
                "contexto": 10,
                "novedad": 10,
                "gancho": 5,
            },
            "categoria": "jugada",
            "gancho": HOOK_A,
            "chat": {"msg_min": 60.0, "multiplicador": 5.0},
        },
        {
            "inicio": "00:50:10",
            "fin": "00:50:50",
            "puntuacion": 20,
            "desglose": {
                "reaccion_chat": 2,
                "contexto": 8,
                "novedad": 5,
                "gancho": 5,
            },
            "categoria": "jugada",
            "gancho": HOOK_QUIET,
            "chat": {"msg_min": 13.0, "multiplicador": 13 / 12},
        },
        {
            "inicio": "00:00:15",
            "fin": "00:00:55",
            "puntuacion": 7,
            "desglose": {
                "reaccion_chat": 2,
                "contexto": 2,
                "novedad": 2,
                "gancho": 1,
            },
            "categoria": "jugada",
            "gancho": HOOK_FILLER,
            "chat": {"msg_min": 13.0, "multiplicador": 13 / 12},
        },
    ]


def test_output_is_capped_at_the_moment_limit_although_twenty_are_judged(tmp_path):
    judge = FakeJudge(demo_outcomes())

    moments, out_path, _ = run_demo(tmp_path, judge)

    assert MAX_MOMENTS == 5
    assert len(judge.requests) == 20
    assert len(moments) == MAX_MOMENTS
    assert len(read_output(out_path)) == MAX_MOMENTS


def test_output_is_sorted_by_puntuacion_descending(tmp_path):
    _, out_path, _ = run_demo(tmp_path, FakeJudge(demo_outcomes()))

    scores = [moment["puntuacion"] for moment in read_output(out_path)]

    assert scores == sorted(scores, reverse=True)
    assert scores == [83, 56, 54, 20, 7]


def test_output_follows_the_spec_shape(tmp_path):
    _, out_path, _ = run_demo(tmp_path, FakeJudge(demo_outcomes()))

    for moment in read_output(out_path):
        assert set(moment) == SPEC_MOMENT_KEYS
        assert set(moment["desglose"]) == SPEC_BREAKDOWN_KEYS
        assert set(moment["chat"]) == SPEC_CHAT_KEYS
        assert moment["puntuacion"] == sum(moment["desglose"].values())


def test_output_entries_validate_as_moments(tmp_path):
    _, out_path, _ = run_demo(tmp_path, FakeJudge(demo_outcomes()))

    moments = [Moment.model_validate(entry) for entry in read_output(out_path)]

    assert len(moments) == 5


def test_returned_moments_match_the_file(tmp_path):
    moments, out_path, _ = run_demo(tmp_path, FakeJudge(demo_outcomes()))

    assert [m.model_dump(mode="json") for m in moments] == read_output(out_path)


def test_output_keeps_non_ascii_characters_unescaped(tmp_path):
    _, out_path, _ = run_demo(tmp_path, FakeJudge(demo_outcomes()))

    text = out_path.read_text(encoding="utf-8")

    assert HOOK_B in text
    assert "¡Qué barbaridad" in text
    assert "España" in text
    assert "\\u" not in text


def test_output_is_utf8_with_a_trailing_newline(tmp_path):
    _, out_path, _ = run_demo(tmp_path, FakeJudge(demo_outcomes()))

    raw = out_path.read_bytes()

    assert raw.decode("utf-8").endswith("]\n")
    assert "ñ".encode() in raw
    assert not raw.startswith(b"\xef\xbb\xbf")


def test_judge_receives_the_twenty_demo_candidates_planted_peaks_first(tmp_path):
    judge = FakeJudge(demo_outcomes())

    run_demo(tmp_path, judge)

    planted = judge.requests[:3]
    fillers = judge.requests[3:]
    assert len(judge.requests) == 20
    assert [
        (c.start_s, c.end_s, c.msg_min, c.multiplier, c.reaction_points)
        for c in planted
    ] == [
        (540.0, 675.0, 60, 5.0, 29.0),
        (1978.0, 2113.0, 48, 4.0, 28.0),
        (4139.0, 4274.0, 30, 2.5, 21.0),
    ]
    assert [c.start_s for c in fillers] == list(FILLER_STARTS)
    assert all(c.end_s - c.start_s == CANDIDATE_LENGTH_S for c in fillers)
    assert all(c.msg_min == 13 for c in fillers)
    assert all(c.multiplier == pytest.approx(13 / 12) for c in fillers)
    assert all(c.reaction_points == pytest.approx(5 / 3) for c in fillers)
    assert all(c.reaction_points < 2 for c in fillers)


def test_demo_candidates_start_with_the_planted_peaks_and_then_fill_up_to_twenty():
    candidates = generate_candidates(load_chat(CHAT))

    assert [c.start_s for c in candidates] == list(DEMO_STARTS)
    assert [c.reaction_points for c in candidates[:3]] == [29.0, 28.0, 21.0]
    assert all(c.reaction_points < 2 for c in candidates[3:])


def test_demo_reference_no_longer_discriminates_because_twenty_candidates_cover_all_clips():
    candidates = generate_candidates(load_chat(CHAT))
    reference = load_reference(REFERENCE)

    covered = [
        any(window_matches(c.start_s, c.end_s, clip) for c in candidates)
        for clip in reference
    ]

    assert covered == [True, True, True]


# run: printed lines


def test_printed_lines_without_reference_and_without_usage(tmp_path):
    _, out_path, lines = run_demo(tmp_path, FakeJudge(demo_outcomes()))

    assert lines == [
        f"Moments: 5 written to {out_path}",
        "Candidate errors: 0",
        "Judge usage: not reported by this judge",
        PENDING_REVIEW,
    ]


def test_usage_line_reports_calls_and_tokens(tmp_path):
    judge = UsageJudge(demo_outcomes())

    _, _, lines = run_demo(tmp_path, judge)

    assert "Judge usage: 20 calls, 2000 input tokens, 500 output tokens" in lines
    assert "Judge usage: not reported by this judge" not in lines


def test_pending_review_is_always_the_last_line(tmp_path):
    outcomes = demo_outcomes()
    outcomes[540.0] = [JudgeError("boom"), JudgeError("boom")]

    for judge, reference in (
        (FakeJudge(demo_outcomes()), None),
        (UsageJudge(demo_outcomes()), REFERENCE),
        (FakeJudge(outcomes), REFERENCE),
    ):
        *_, lines = run_demo(tmp_path, judge, reference)
        assert lines[-1] == PENDING_REVIEW


def test_pending_review_line_states_nothing_is_uploaded():
    assert PENDING_REVIEW == (
        "Pending human review: this agent never uploads or publishes anything."
    )


def test_a_candidate_failing_twice_is_reported_and_not_fatal(tmp_path):
    outcomes = demo_outcomes()
    outcomes[540.0] = [JudgeError("rate limited"), JudgeError("rate limited")]
    judge = FakeJudge(outcomes)

    moments, out_path, lines = run_demo(tmp_path, judge)

    assert len(moments) == MAX_MOMENTS
    hooks = [m["gancho"] for m in read_output(out_path)]
    assert hooks == [HOOK_B, HOOK_C, HOOK_QUIET, HOOK_FILLER, HOOK_FILLER]
    assert HOOK_A not in hooks
    assert lines == [
        f"Moments: 5 written to {out_path}",
        "Candidate errors: 1",
        "  - candidate 00:09:00-00:11:15: rate limited",
        "Judge usage: not reported by this judge",
        PENDING_REVIEW,
    ]
    assert [c.start_s for c in judge.requests].count(540.0) == 2
    assert len(judge.requests) == 21


def test_every_failing_candidate_gets_its_own_error_line(tmp_path):
    outcomes = demo_outcomes()
    outcomes[540.0] = [JudgeError("first"), JudgeError("first")]
    outcomes[1978.0] = [JudgeError("second"), JudgeError("second")]

    _, _, lines = run_demo(tmp_path, FakeJudge(outcomes))

    assert lines[1:4] == [
        "Candidate errors: 2",
        "  - candidate 00:09:00-00:11:15: first",
        "  - candidate 00:32:58-00:35:13: second",
    ]


def failing_judge(judge_class, message="down"):
    return judge_class({}, default=failing_default(message))


def demo_window_label(start_s):
    return (
        f"candidate {seconds_to_hhmmss(start_s)}-"
        f"{seconds_to_hhmmss(start_s + CANDIDATE_LENGTH_S)}"
    )


def demo_error_lines(reason):
    return [f"  - {demo_window_label(start_s)}: {reason}" for start_s in DEMO_STARTS]


TOTAL_FAILURE_LINES = [
    "Candidate errors: 20",
    *demo_error_lines("down"),
    "Judge usage: not reported by this judge",
]

TOTAL_FAILURE_MESSAGE = "all 20 candidates failed; output not written"


def run_total_failure(tmp_path, judge, reference=None, out_path=None):
    out_path = tmp_path / "resultados.json" if out_path is None else out_path
    stream = io.StringIO()
    with pytest.raises(main_module.AllCandidatesFailedError) as error_info:
        run(TRANSCRIPT, CHAT, out_path, judge, reference, stream)
    return error_info.value, stream.getvalue().splitlines()


def test_the_demo_error_labels_start_with_the_planted_windows():
    assert demo_error_lines("x")[:3] == [
        "  - candidate 00:09:00-00:11:15: x",
        "  - candidate 00:32:58-00:35:13: x",
        "  - candidate 01:08:59-01:11:14: x",
    ]
    assert len(TOTAL_FAILURE_LINES) == 22


def test_all_candidates_failing_raises_and_does_not_create_the_output(tmp_path):
    error, _ = run_total_failure(tmp_path, failing_judge(FakeJudge))

    assert str(error) == TOTAL_FAILURE_MESSAGE
    assert not (tmp_path / "resultados.json").exists()
    assert list(tmp_path.iterdir()) == []


def test_all_candidates_failed_error_is_a_runtime_error():
    assert issubclass(main_module.AllCandidatesFailedError, RuntimeError)


def test_all_candidates_failing_keeps_an_existing_output_byte_for_byte(tmp_path):
    out_path = tmp_path / "resultados.json"
    previous = b'[{"previous": "run"}]\n'
    out_path.write_bytes(previous)

    run_total_failure(tmp_path, failing_judge(FakeJudge), out_path=out_path)

    assert out_path.read_bytes() == previous


def test_all_candidates_failing_prints_only_the_errors_and_the_usage(tmp_path):
    _, lines = run_total_failure(tmp_path, failing_judge(FakeJudge))

    assert lines == TOTAL_FAILURE_LINES
    assert not any(line.startswith("Moments:") for line in lines)
    assert PENDING_REVIEW not in lines


def test_all_candidates_failing_prints_the_usage_of_a_reporting_judge(tmp_path):
    _, lines = run_total_failure(tmp_path, failing_judge(UsageJudge))

    assert lines[-1] == "Judge usage: 40 calls, 4000 input tokens, 1000 output tokens"


def test_all_candidates_failing_prints_no_evaluation_with_a_reference(tmp_path):
    judge = failing_judge(FakeJudge)

    error, lines = run_total_failure(tmp_path, judge, reference=REFERENCE)

    assert lines == TOTAL_FAILURE_LINES
    assert not any(line.startswith("Evaluation") for line in lines)
    assert "detected" not in " ".join(lines)
    assert str(error) == TOTAL_FAILURE_MESSAGE


def test_candidates_without_transcript_all_fail_like_judge_errors(tmp_path):
    transcript = write_json(
        tmp_path,
        "late_transcript.json",
        [{"start_s": 9000, "end_s": 9030, "text": "Esto queda lejos de todo"}],
    )
    judge = FakeJudge({})
    out_path = tmp_path / "resultados.json"
    stream = io.StringIO()

    with pytest.raises(main_module.AllCandidatesFailedError, match="all 20 candidates"):
        run(transcript, CHAT, out_path, judge, None, stream)

    assert judge.requests == []
    assert not out_path.exists()
    assert stream.getvalue().splitlines() == [
        "Candidate errors: 20",
        *demo_error_lines("no transcript in the window"),
        "Judge usage: not reported by this judge",
    ]


# run: evaluation


def test_reference_adds_the_evaluation_lines_before_the_pending_line(tmp_path):
    _, out_path, lines = run_demo(tmp_path, UsageJudge(demo_outcomes()), REFERENCE)

    assert lines == [
        f"Moments: 5 written to {out_path}",
        "Candidate errors: 0",
        "Judge usage: 20 calls, 2000 input tokens, 500 output tokens",
        *EVALUATION_LINES,
        PENDING_REVIEW,
    ]


def test_evaluation_reports_the_three_demo_clips_detected(tmp_path):
    _, _, lines = run_demo(tmp_path, FakeJudge(demo_outcomes()), REFERENCE)

    assert [line for line in lines if "Evaluation" in line or "detected" in line] == (
        EVALUATION_LINES
    )


def test_a_clip_whose_candidate_falls_outside_the_top_moments_is_reported_missed(
    tmp_path,
):
    _, _, lines = run_demo(tmp_path, FakeJudge(planted_outcomes()), REFERENCE)

    assert lines[3:7] == [
        "Evaluation: 2/3 reference clips detected (tolerance +/-60 s)",
        "  - 00:10:10-00:10:40: detected",
        "  - 00:33:30-00:34:10: detected",
        "  - 00:50:00-00:50:30: missed",
    ]


def far_reference(tmp_path):
    return write_json(
        tmp_path,
        "far_reference.json",
        [
            {"start_s": 610, "end_s": 640},
            {"start_s": 5100, "end_s": 5130},
        ],
    )


def test_a_clip_far_from_every_candidate_window_is_reported_missed(tmp_path):
    reference = far_reference(tmp_path)

    _, _, lines = run_demo(tmp_path, FakeJudge(demo_outcomes()), reference)

    assert lines[3:6] == [
        "Evaluation: 1/2 reference clips detected (tolerance +/-60 s)",
        "  - 00:10:10-00:10:40: detected",
        "  - 01:25:00-01:25:30: missed",
    ]


def test_the_far_clip_is_more_than_sixty_seconds_past_the_last_candidate_window():
    candidates = generate_candidates(load_chat(CHAT))

    last_end_s = max(c.end_s for c in candidates)

    assert last_end_s == 4940.0
    assert 5100 - last_end_s > 60


def test_no_evaluation_lines_without_reference(tmp_path):
    _, _, lines = run_demo(tmp_path, FakeJudge(demo_outcomes()))

    assert not any(line.startswith("Evaluation") for line in lines)


def test_a_bad_reference_fails_before_any_judge_call(tmp_path):
    judge = FakeJudge(demo_outcomes())
    reference = write_json(tmp_path, "ref.json", [{"inicio": 1, "fin": 2}])
    out_path = tmp_path / "resultados.json"

    with pytest.raises(LoadError, match="missing keys start_s, end_s"):
        run(TRANSCRIPT, CHAT, out_path, judge, reference, io.StringIO())

    assert judge.requests == []
    assert not out_path.exists()


def test_a_missing_reference_file_fails_before_any_judge_call(tmp_path):
    judge = FakeJudge(demo_outcomes())
    out_path = tmp_path / "resultados.json"

    with pytest.raises(LoadError, match="file does not exist"):
        run(TRANSCRIPT, CHAT, out_path, judge, tmp_path / "nope.json", io.StringIO())

    assert judge.requests == []
    assert not out_path.exists()


# run: edge cases


def test_zero_candidates_writes_an_empty_list_and_is_not_an_error(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(main_module, "generate_candidates", lambda *a, **k: [])
    judge = FakeJudge({})
    out_path = tmp_path / "resultados.json"
    stream = io.StringIO()

    moments = run(TRANSCRIPT, CHAT, out_path, judge, None, stream)

    assert moments == []
    assert out_path.read_text(encoding="utf-8") == "[]\n"
    assert judge.requests == []
    assert stream.getvalue().splitlines() == [
        f"Moments: 0 written to {out_path}",
        "Candidate errors: 0",
        "Judge usage: not reported by this judge",
        PENDING_REVIEW,
    ]


def test_flat_chat_is_judged_instead_of_giving_zero_candidates(tmp_path):
    chat = write_json(
        tmp_path,
        "chat.json",
        [{"t_s": second, "message": "hola"} for second in range(0, 600, 5)],
    )
    judge = FakeJudge({})
    out_path = tmp_path / "resultados.json"

    moments = run(TRANSCRIPT, chat, out_path, judge, None, io.StringIO())

    assert [c.start_s for c in judge.requests] == [0.0, 60.0, 180.0, 300.0, 420.0]
    assert [c.reaction_points for c in judge.requests] == [0.0] * 5
    assert len(moments) == 5
    assert len(read_output(out_path)) == 5


def test_chat_without_activity_raises_before_judging_or_writing(tmp_path):
    chat = write_json(tmp_path, "empty_chat.json", [])
    judge = FakeJudge({})
    out_path = tmp_path / "resultados.json"

    with pytest.raises(InsufficientChatError, match="chat sin actividad suficiente"):
        run(TRANSCRIPT, chat, out_path, judge, None, io.StringIO())

    assert judge.requests == []
    assert not out_path.exists()


def test_run_prints_to_stdout_by_default(tmp_path, capsys):
    out_path = tmp_path / "resultados.json"

    run(TRANSCRIPT, CHAT, out_path, FakeJudge(demo_outcomes()))

    captured = capsys.readouterr()
    assert captured.out.splitlines()[-1] == PENDING_REVIEW
    assert captured.err == ""


# main


def cli_args(tmp_path, **overrides):
    values = {
        "--transcript": TRANSCRIPT,
        "--chat": CHAT,
        "--out": tmp_path / "resultados.json",
    }
    values.update(overrides)
    return [
        part
        for key, value in values.items()
        if value is not None
        for part in (key, str(value))
    ]


@pytest.fixture
def fake_judge(monkeypatch):
    judge = UsageJudge(demo_outcomes())
    monkeypatch.setattr(main_module, "GeminiJudge", lambda: judge)
    return judge


def test_main_without_api_key_exits_non_zero_and_names_the_variable(tmp_path, capsys):
    code = main(cli_args(tmp_path))

    captured = capsys.readouterr()
    assert code == EXIT_FATAL
    assert code != 0
    assert captured.err.startswith("error: ")
    assert "GEMINI_API_KEY" in captured.err
    assert not (tmp_path / "resultados.json").exists()


def test_main_happy_path_exits_zero_and_writes_the_output(tmp_path, capsys, fake_judge):
    code = main(cli_args(tmp_path))

    captured = capsys.readouterr()
    out_path = tmp_path / "resultados.json"
    assert code == EXIT_OK == 0
    assert out_path.is_file()
    assert len(read_output(out_path)) == 5
    assert captured.out.splitlines()[-1] == PENDING_REVIEW
    assert captured.err == ""


def test_main_with_reference_prints_the_evaluation(tmp_path, capsys, fake_judge):
    code = main(cli_args(tmp_path, **{"--reference": REFERENCE}))

    lines = capsys.readouterr().out.splitlines()
    assert code == 0
    for expected in EVALUATION_LINES:
        assert expected in lines


def test_main_missing_transcript_file_exits_one_with_an_error(
    tmp_path, capsys, fake_judge
):
    code = main(cli_args(tmp_path, **{"--transcript": tmp_path / "nope.json"}))

    captured = capsys.readouterr()
    assert code == EXIT_FATAL == 1
    assert captured.err.startswith("error: ")
    assert "nope.json" in captured.err
    assert "file does not exist" in captured.err
    assert fake_judge.calls == 0
    assert not (tmp_path / "resultados.json").exists()


def test_main_bad_reference_exits_one_without_judging(tmp_path, capsys, fake_judge):
    reference = write_json(tmp_path, "ref.json", [{"start_s": 5, "end_s": 5}])

    code = main(cli_args(tmp_path, **{"--reference": reference}))

    captured = capsys.readouterr()
    assert code == 1
    assert "error: " in captured.err
    assert "end_s must be greater than start_s" in captured.err
    assert fake_judge.calls == 0
    assert not (tmp_path / "resultados.json").exists()


def test_main_empty_reference_exits_one_without_judging(tmp_path, capsys, fake_judge):
    reference = write_json(tmp_path, "empty_reference.json", [])

    code = main(cli_args(tmp_path, **{"--reference": reference}))

    captured = capsys.readouterr()
    assert code == 1
    assert captured.err == "error: empty_reference.json: reference has no clips\n"
    assert fake_judge.calls == 0
    assert not (tmp_path / "resultados.json").exists()


@pytest.mark.parametrize("last_s", [172801, 1e9, 1e15])
def test_main_chat_longer_than_48_hours_exits_one_without_judging(
    tmp_path, capsys, fake_judge, last_s
):
    chat = write_json(
        tmp_path,
        "chat.json",
        [{"t_s": 5, "message": "x"}, {"t_s": last_s, "message": "y"}],
    )

    code = main(cli_args(tmp_path, **{"--chat": chat}))

    captured = capsys.readouterr()
    assert code == EXIT_FATAL
    assert captured.err.startswith("error: chat spans ")
    assert str(int(last_s)) in captured.err
    assert "Traceback" not in captured.err
    assert fake_judge.calls == 0
    assert not (tmp_path / "resultados.json").exists()


def test_main_sparse_chat_below_the_mean_floor_exits_one_without_judging(
    tmp_path, capsys, fake_judge
):
    chat = write_json(
        tmp_path,
        "chat.json",
        [{"t_s": 0, "message": "x"}, {"t_s": 3000, "message": "y"}],
    )

    code = main(cli_args(tmp_path, **{"--chat": chat}))

    captured = capsys.readouterr()
    assert code == EXIT_FATAL
    assert captured.err == "error: chat sin actividad suficiente\n"
    assert fake_judge.calls == 0
    assert not (tmp_path / "resultados.json").exists()


def test_main_chat_without_activity_exits_one(tmp_path, capsys, fake_judge):
    chat = write_json(tmp_path, "chat.json", [])

    code = main(cli_args(tmp_path, **{"--chat": chat}))

    captured = capsys.readouterr()
    assert code == EXIT_FATAL
    assert captured.err == "error: chat sin actividad suficiente\n"
    assert fake_judge.calls == 0
    assert not (tmp_path / "resultados.json").exists()


def test_main_undecodable_input_exits_one_instead_of_crashing(
    tmp_path, capsys, fake_judge
):
    transcript = tmp_path / "transcript.json"
    transcript.write_bytes(b"\xff\xfe\x00 not utf-8 \xff")

    code = main(cli_args(tmp_path, **{"--transcript": transcript}))

    assert code == EXIT_FATAL
    assert capsys.readouterr().err.startswith("error: ")


def test_main_unwritable_output_exits_one(tmp_path, capsys, fake_judge):
    out_path = tmp_path / "missing_dir" / "resultados.json"

    code = main(cli_args(tmp_path, **{"--out": out_path}))

    assert code == EXIT_FATAL
    assert capsys.readouterr().err.startswith("error: ")


def test_main_all_candidates_failing_exits_one_and_leaves_no_output(
    tmp_path, capsys, monkeypatch
):
    monkeypatch.setattr(main_module, "GeminiJudge", lambda: failing_judge(UsageJudge))

    code = main(cli_args(tmp_path))

    captured = capsys.readouterr()
    assert code == EXIT_FATAL == 1
    assert captured.err == "error: all 20 candidates failed; output not written\n"
    assert "Moments:" not in captured.out
    assert PENDING_REVIEW not in captured.out
    assert "Candidate errors: 20" in captured.out
    assert not (tmp_path / "resultados.json").exists()


def test_main_all_candidates_failing_keeps_an_existing_output(
    tmp_path, capsys, monkeypatch
):
    out_path = tmp_path / "resultados.json"
    out_path.write_text("previous content\n", encoding="utf-8")
    monkeypatch.setattr(main_module, "GeminiJudge", lambda: failing_judge(UsageJudge))

    code = main(cli_args(tmp_path))

    assert code == EXIT_FATAL
    assert out_path.read_text(encoding="utf-8") == "previous content\n"


def test_main_all_candidates_failing_with_reference_prints_no_evaluation(
    tmp_path, capsys, monkeypatch
):
    monkeypatch.setattr(main_module, "GeminiJudge", lambda: failing_judge(UsageJudge))

    code = main(cli_args(tmp_path, **{"--reference": REFERENCE}))

    captured = capsys.readouterr()
    assert code == EXIT_FATAL
    assert "Evaluation" not in captured.out
    assert not (tmp_path / "resultados.json").exists()


def test_main_candidates_without_transcript_exit_one(tmp_path, capsys, fake_judge):
    transcript = write_json(
        tmp_path,
        "late_transcript.json",
        [{"start_s": 9000, "end_s": 9030, "text": "Esto queda lejos de todo"}],
    )

    code = main(cli_args(tmp_path, **{"--transcript": transcript}))

    captured = capsys.readouterr()
    assert code == EXIT_FATAL
    assert captured.err == "error: all 20 candidates failed; output not written\n"
    assert fake_judge.calls == 0
    assert not (tmp_path / "resultados.json").exists()


def test_main_partial_failure_exits_zero_and_writes_the_moments(
    tmp_path, capsys, monkeypatch
):
    outcomes = demo_outcomes()
    outcomes[540.0] = [JudgeError("rate limited"), JudgeError("rate limited")]
    monkeypatch.setattr(main_module, "GeminiJudge", lambda: UsageJudge(outcomes))

    code = main(cli_args(tmp_path))

    captured = capsys.readouterr()
    assert code == EXIT_OK
    assert captured.err == ""
    assert len(read_output(tmp_path / "resultados.json")) == 5
    assert "Candidate errors: 1" in captured.out
    assert "  - candidate 00:09:00-00:11:15: rate limited" in captured.out
    assert captured.out.splitlines()[-1] == PENDING_REVIEW


def test_main_zero_candidates_exits_zero_and_writes_an_empty_list(
    tmp_path, capsys, monkeypatch
):
    judge = UsageJudge({})
    monkeypatch.setattr(main_module, "GeminiJudge", lambda: judge)
    monkeypatch.setattr(main_module, "generate_candidates", lambda *a, **k: [])

    code = main(cli_args(tmp_path))

    captured = capsys.readouterr()
    assert code == EXIT_OK
    assert captured.err == ""
    assert (tmp_path / "resultados.json").read_text(encoding="utf-8") == "[]\n"
    assert "Moments: 0 written to" in captured.out
    assert judge.calls == 0


def test_main_flat_chat_exits_zero_with_judged_candidates(
    tmp_path, capsys, monkeypatch
):
    chat = write_json(
        tmp_path,
        "flat_chat.json",
        [{"t_s": second, "message": "hola"} for second in range(0, 600, 5)],
    )
    judge = UsageJudge({})
    monkeypatch.setattr(main_module, "GeminiJudge", lambda: judge)

    code = main(cli_args(tmp_path, **{"--chat": chat}))

    captured = capsys.readouterr()
    assert code == EXIT_OK
    assert captured.err == ""
    assert "Moments: 5 written to" in captured.out
    assert judge.calls == 5


def test_main_corrupt_csv_exits_one_naming_the_file(tmp_path, capsys, fake_judge):
    chat = tmp_path / "broken_chat.csv"
    chat.write_text('t_s,message\n1,"' + "a" * 140_000 + "\n", encoding="utf-8")

    code = main(cli_args(tmp_path, **{"--chat": chat}))

    captured = capsys.readouterr()
    assert code == EXIT_FATAL
    assert captured.err.startswith("error: broken_chat.csv: invalid CSV")
    assert "Traceback" not in captured.err
    assert fake_judge.calls == 0
    assert not (tmp_path / "resultados.json").exists()


# output path preflight


class InterruptingJudge(UsageJudge):
    def judge(self, candidate, segments):
        raise KeyboardInterrupt


class FakeGenaiClient:
    class models:
        @staticmethod
        def generate_content(*, model, contents, config):
            raise AssertionError("not called in these tests")


def copy_inputs(tmp_path):
    transcript = tmp_path / "transcript.json"
    chat = tmp_path / "chat.json"
    reference = tmp_path / "reference.json"
    shutil.copy(TRANSCRIPT, transcript)
    shutil.copy(CHAT, chat)
    shutil.copy(REFERENCE, reference)
    return transcript, chat, reference


def test_output_path_that_is_a_directory_exits_one_before_judging(
    tmp_path, capsys, fake_judge
):
    out_path = tmp_path / "out_dir"
    out_path.mkdir()

    code = main(cli_args(tmp_path, **{"--out": out_path}))

    captured = capsys.readouterr()
    assert code == EXIT_FATAL
    assert captured.err.startswith(f"error: {out_path}")
    assert "is a directory" in captured.err
    assert fake_judge.calls == 0
    assert fake_judge.requests == []
    assert out_path.is_dir()


def test_output_whose_parent_is_missing_exits_one_before_judging(
    tmp_path, capsys, fake_judge
):
    out_path = tmp_path / "missing_dir" / "resultados.json"

    code = main(cli_args(tmp_path, **{"--out": out_path}))

    captured = capsys.readouterr()
    assert code == EXIT_FATAL
    assert captured.err.startswith(f"error: {out_path}")
    assert "parent directory does not exist" in captured.err
    assert fake_judge.calls == 0
    assert fake_judge.requests == []
    assert not out_path.parent.exists()


@pytest.mark.skipif(
    not hasattr(os, "geteuid") or os.geteuid() == 0,
    reason="file permissions are not enforced for root",
)
def test_read_only_output_exits_one_before_judging_and_is_untouched(
    tmp_path, capsys, fake_judge
):
    out_path = tmp_path / "resultados.json"
    out_path.write_text("previous content\n", encoding="utf-8")
    out_path.chmod(0o444)
    try:
        code = main(cli_args(tmp_path))
    finally:
        out_path.chmod(0o644)

    captured = capsys.readouterr()
    assert code == EXIT_FATAL
    assert captured.err.startswith(f"error: {out_path}")
    assert "not writable" in captured.err
    assert fake_judge.calls == 0
    assert fake_judge.requests == []
    assert out_path.read_text(encoding="utf-8") == "previous content\n"


@pytest.mark.parametrize("which", ["transcript", "chat", "reference"])
def test_output_equal_to_an_input_exits_one_and_leaves_it_untouched(
    tmp_path, capsys, fake_judge, which
):
    transcript, chat, reference = copy_inputs(tmp_path)
    target = {"transcript": transcript, "chat": chat, "reference": reference}[which]
    before = target.read_bytes()

    code = main(
        [
            "--transcript",
            str(transcript),
            "--chat",
            str(chat),
            "--reference",
            str(reference),
            "--out",
            str(target),
        ]
    )

    captured = capsys.readouterr()
    assert code == EXIT_FATAL
    assert captured.err.startswith(f"error: {target}")
    assert f"would overwrite the input file {target.name}" in captured.err
    assert fake_judge.calls == 0
    assert fake_judge.requests == []
    assert target.read_bytes() == before


def test_output_reaching_an_input_through_a_symlink_is_rejected(
    tmp_path, capsys, fake_judge
):
    transcript, chat, _ = copy_inputs(tmp_path)
    link = tmp_path / "link.json"
    try:
        link.symlink_to(transcript)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not available")
    before = transcript.read_bytes()

    code = main(
        [
            "--transcript",
            str(transcript),
            "--chat",
            str(chat),
            "--out",
            str(link),
        ]
    )

    assert code == EXIT_FATAL
    assert "would overwrite the input file" in capsys.readouterr().err
    assert fake_judge.calls == 0
    assert transcript.read_bytes() == before


def test_failed_preflight_does_not_create_the_output_file(tmp_path, capsys, fake_judge):
    transcript, chat, _ = copy_inputs(tmp_path)
    out_path = tmp_path / "nowhere" / "resultados.json"

    code = main(
        ["--transcript", str(transcript), "--chat", str(chat), "--out", str(out_path)]
    )

    assert code == EXIT_FATAL
    assert not out_path.exists()
    assert not out_path.parent.exists()
    assert sorted(path.name for path in tmp_path.iterdir()) == [
        "chat.json",
        "reference.json",
        "transcript.json",
    ]


def test_preflight_of_a_valid_new_output_leaves_no_file_until_the_run_ends(
    tmp_path, capsys
):
    judge = FakeJudge(demo_outcomes())
    out_path = tmp_path / "resultados.json"
    seen = []

    original_judge = judge.judge

    def spying_judge(candidate, segments):
        seen.append(out_path.exists())
        return original_judge(candidate, segments)

    judge.judge = spying_judge

    run(TRANSCRIPT, CHAT, out_path, judge, None, io.StringIO())

    assert seen == [False] * 20
    assert out_path.is_file()


def test_run_raises_output_path_error_before_loading_inputs(tmp_path):
    judge = FakeJudge(demo_outcomes())
    out_path = tmp_path / "out_dir"
    out_path.mkdir()

    with pytest.raises(main_module.OutputPathError, match="is a directory"):
        run(tmp_path / "nope.json", tmp_path / "nope2.json", out_path, judge)

    assert judge.requests == []


def test_output_path_error_is_a_value_error():
    assert issubclass(main_module.OutputPathError, ValueError)


# interruption


def test_keyboard_interrupt_from_the_judge_returns_130(tmp_path, capsys, monkeypatch):
    judge = InterruptingJudge(demo_outcomes())
    monkeypatch.setattr(main_module, "GeminiJudge", lambda: judge)

    code = main(cli_args(tmp_path))

    captured = capsys.readouterr()
    assert code == main_module.EXIT_INTERRUPTED == 130
    assert captured.err == "error: interrupted\n"
    assert "Traceback" not in captured.err


# secrets


SENTINEL_KEY = "sentinel-key-123"


def test_the_api_key_never_appears_in_output_on_a_happy_run(
    tmp_path, capsys, monkeypatch, fake_judge
):
    monkeypatch.setenv("GEMINI_API_KEY", SENTINEL_KEY)

    code = main(cli_args(tmp_path, **{"--reference": REFERENCE}))

    captured = capsys.readouterr()
    assert code == EXIT_OK
    assert SENTINEL_KEY not in captured.out
    assert SENTINEL_KEY not in captured.err
    assert SENTINEL_KEY not in (tmp_path / "resultados.json").read_text(
        encoding="utf-8"
    )


def test_the_api_key_never_appears_in_output_on_a_fatal_error(
    tmp_path, capsys, monkeypatch, fake_judge
):
    monkeypatch.setenv("GEMINI_API_KEY", SENTINEL_KEY)

    code = main(cli_args(tmp_path, **{"--transcript": tmp_path / "nope.json"}))

    captured = capsys.readouterr()
    assert code == EXIT_FATAL
    assert captured.err.startswith("error: ")
    assert SENTINEL_KEY not in captured.out
    assert SENTINEL_KEY not in captured.err


# usage reporting contract


def test_gemini_judge_satisfies_the_reports_usage_protocol():
    judge = GeminiJudge(client=FakeGenaiClient())

    assert isinstance(judge, ReportsUsage)
    assert judge.calls == 0
    assert judge.input_tokens == 0
    assert judge.output_tokens == 0


class ScriptedGenaiClient:
    def __init__(self, texts, usage):
        self._texts = list(texts)
        self._usage = usage
        self.models = self

    def generate_content(self, *, model, contents, config):
        return types.GenerateContentResponse(
            candidates=[
                types.Candidate(
                    content=types.Content(parts=[types.Part(text=self._texts.pop(0))])
                )
            ],
            usage_metadata=self._usage,
        )


def test_gemini_judge_with_a_fake_client_prints_numeric_usage(
    tmp_path, capsys, monkeypatch
):
    texts = [
        make_judgment(
            start_s + 10, start_s + 50, "gancho", 10, 10, 10
        ).model_dump_json()
        for start_s in DEMO_STARTS
    ]
    usage = types.GenerateContentResponseUsageMetadata(
        prompt_token_count=1000, candidates_token_count=60, thoughts_token_count=40
    )
    judge = GeminiJudge(
        client=ScriptedGenaiClient(texts, usage), sleeper=lambda seconds: None
    )
    monkeypatch.setattr(main_module, "GeminiJudge", lambda: judge)

    code = main(cli_args(tmp_path))

    lines = capsys.readouterr().out.splitlines()
    assert code == EXIT_OK
    assert isinstance(judge, ReportsUsage)
    assert "Judge usage: 20 calls, 20000 input tokens, 2000 output tokens" in lines
    usage_line = next(line for line in lines if line.startswith("Judge usage:"))
    assert [int(number) for number in re.findall(r"\d+", usage_line)] == [
        20,
        20000,
        2000,
    ]


@pytest.mark.parametrize("missing", ["--transcript", "--chat", "--out"])
def test_main_missing_required_argument_exits_with_code_two(
    tmp_path, capsys, fake_judge, missing
):
    with pytest.raises(SystemExit) as exit_info:
        main(cli_args(tmp_path, **{missing: None}))

    assert exit_info.value.code == 2
    assert missing in capsys.readouterr().err
    assert fake_judge.calls == 0


def test_main_unknown_argument_exits_with_code_two(tmp_path, capsys, fake_judge):
    with pytest.raises(SystemExit) as exit_info:
        main([*cli_args(tmp_path), "--upload"])

    assert exit_info.value.code == 2


def test_the_cli_offers_no_upload_or_publish_option():
    parser = main_module._parser()

    options = {option for action in parser._actions for option in action.option_strings}

    assert options == {"-h", "--help", "--transcript", "--chat", "--out", "--reference"}


# subprocess (never builds the judge)


def run_cli(*args):
    return subprocess.run(
        [sys.executable, "-m", "src.main", *args],
        check=False,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_cli_help_lists_the_arguments():
    result = run_cli("--help")

    assert result.returncode == 0
    for option in ("--transcript", "--chat", "--out", "--reference"):
        assert option in result.stdout


def test_cli_without_arguments_exits_with_code_two():
    result = run_cli()

    assert result.returncode == 2
    assert "required" in result.stderr
