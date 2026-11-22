import itertools
import json

import pytest
from google.genai import errors as genai_errors
from google.genai import types
from pydantic import ValidationError

import src.judge as judge_module
from src.judge import (
    DEFAULT_GEMINI_MODEL,
    MAX_RETRY_DELAY_S,
    MAX_TRANSIENT_ATTEMPTS,
    MIN_CALL_INTERVAL_S,
    TRANSIENT_BACKOFF_S,
    GeminiJudge,
    JudgeConfigError,
    JudgeError,
    Judgment,
    TransientJudgeError,
    build_prompt,
    judge_candidates,
    round_half_up,
    segments_in_window,
)
from src.models import Candidate, Segment


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


def make_candidate(start_s=100.0, end_s=235.0, reaction_points=15.0, **overrides):
    values = {
        "start_s": start_s,
        "end_s": end_s,
        "msg_min": 120,
        "multiplier": 3.2,
        "reaction_points": reaction_points,
    }
    values.update(overrides)
    return Candidate(**values)


def make_judgment(start_s, end_s, context=10, novelty=10, hook=10, **overrides):
    values = {
        "start_s": start_s,
        "end_s": end_s,
        "category": "jugada",
        "hook": "Mira esto",
        "context_score": context,
        "novelty_score": novelty,
        "hook_score": hook,
    }
    values.update(overrides)
    return Judgment(**values)


def make_segments(*spans):
    return [
        Segment(start_s=start, end_s=end, text=f"texto {start:g}-{end:g}")
        for start, end in spans
    ]


WIDE_TRANSCRIPT = make_segments((0, 5000))


def validation_error():
    try:
        Judgment.model_validate({"start_s": 1, "end_s": 2})
    except ValidationError as error:
        return error
    raise AssertionError("expected a ValidationError")


class FakeJudge:
    def __init__(self, outcomes):
        self._outcomes = {key: list(values) for key, values in outcomes.items()}
        self.calls = []

    def judge(self, candidate, segments):
        self.calls.append((candidate, list(segments)))
        outcome = self._outcomes[candidate.start_s].pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def calls_for(self, start_s):
        return [call for call in self.calls if call[0].start_s == start_s]


def make_response(text, usage=None):
    return types.GenerateContentResponse(
        candidates=[
            types.Candidate(content=types.Content(parts=[types.Part(text=text)]))
        ],
        usage_metadata=usage,
    )


def make_usage(prompt=None, candidates=None, thoughts=None):
    return types.GenerateContentResponseUsageMetadata(
        prompt_token_count=prompt,
        candidates_token_count=candidates,
        thoughts_token_count=thoughts,
    )


class FakeClock:
    def __init__(self):
        self.now = 1000.0
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class FakeModels:
    def __init__(self, outcomes, clock=None):
        self._outcomes = list(outcomes)
        self._clock = clock
        self.requests = []
        self.call_times = []

    def generate_content(self, *, model, contents, config):
        self.requests.append({"model": model, "contents": contents, "config": config})
        if self._clock is not None:
            self.call_times.append(self._clock.now)
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FakeClient:
    def __init__(self, *outcomes, clock=None):
        self.models = FakeModels(outcomes, clock)


def make_paced_judge(*outcomes):
    clock = FakeClock()
    client = FakeClient(*outcomes, clock=clock)
    judge = GeminiJudge(client=client, clock=clock, sleeper=clock.sleep)
    return judge, client, clock


def api_error(code, retry_delay=None, status=None):
    details = [
        {
            "@type": "type.googleapis.com/google.rpc.QuotaFailure",
            "violations": [{"quotaMetric": "requests"}],
        }
    ]
    if retry_delay is not None:
        details.append(
            {
                "@type": "type.googleapis.com/google.rpc.RetryInfo",
                "retryDelay": retry_delay,
            }
        )
    cls = genai_errors.ClientError if code < 500 else genai_errors.ServerError
    return cls(
        code,
        {
            "error": {
                "code": code,
                "message": f"provider said {code}",
                "status": status or "ERROR",
                "details": details,
            }
        },
    )


def rate_limit_error(retry_delay=None):
    return api_error(429, retry_delay, "RESOURCE_EXHAUSTED")


def unavailable_error():
    return api_error(503, None, "UNAVAILABLE")


def judgment_json(**overrides):
    values = {
        "start_s": 110.9,
        "end_s": 160.7,
        "category": "bug gracioso",
        "hook": "El coche vuela",
        "context_score": 20,
        "novelty_score": 15,
        "hook_score": 12,
    }
    values.update(overrides)
    return json.dumps(values)


# Judgment validation


def test_judgment_accepts_a_valid_payload():
    judgment = make_judgment(10, 20, context=25, novelty=0, hook=20)
    assert (judgment.start_s, judgment.end_s) == (10, 20)
    assert judgment.category == "jugada"


def test_judgment_rejects_a_category_outside_the_closed_list():
    with pytest.raises(ValidationError):
        make_judgment(10, 20, category="meme")


@pytest.mark.parametrize(
    "field, value",
    [
        ("context_score", 26),
        ("context_score", -1),
        ("novelty_score", 26),
        ("novelty_score", -1),
        ("hook_score", 21),
        ("hook_score", -1),
    ],
)
def test_judgment_rejects_scores_out_of_range(field, value):
    with pytest.raises(ValidationError):
        make_judgment(10, 20, **{field: value})


@pytest.mark.parametrize("hook", ["", "   "])
def test_judgment_rejects_a_blank_hook(hook):
    with pytest.raises(ValidationError):
        make_judgment(10, 20, hook=hook)


@pytest.mark.parametrize("start_s, end_s", [(20, 20), (30, 20)])
def test_judgment_requires_end_after_start(start_s, end_s):
    with pytest.raises(ValidationError):
        make_judgment(start_s, end_s)


def test_judgment_rejects_extra_fields():
    payload = make_judgment(10, 20).model_dump()
    payload["reaccion_chat"] = 30
    with pytest.raises(ValidationError):
        Judgment.model_validate(payload)


# segments_in_window and round_half_up


def test_segments_in_window_keeps_overlapping_and_partial_segments():
    segments = make_segments((0, 10), (90, 110), (150, 160), (230, 240), (300, 310))
    selected = segments_in_window(segments, 100, 235)
    assert [(s.start_s, s.end_s) for s in selected] == [
        (90, 110),
        (150, 160),
        (230, 240),
    ]


def test_segments_in_window_excludes_touching_segments():
    segments = make_segments((50, 100), (235, 260))
    assert segments_in_window(segments, 100, 235) == []


@pytest.mark.parametrize(
    "value, expected",
    [(0.0, 0), (14.4, 14), (14.5, 15), (15.5, 16), (16.5, 17), (29.99, 30)],
)
def test_round_half_up(value, expected):
    assert round_half_up(value) == expected


def test_round_half_up_differs_from_bankers_rounding():
    assert round(14.5) == 14
    assert round_half_up(14.5) == 15


# judge_candidates: assembling the Moment


def test_judge_candidates_assembles_the_full_moment():
    candidate = make_candidate(100, 235, reaction_points=15.5)
    judgment = make_judgment(
        110.9, 160.7, context=20, novelty=15, hook=12, category="bug gracioso"
    )
    judge = FakeJudge({100: [judgment]})

    moments, errors = judge_candidates([candidate], WIDE_TRANSCRIPT, judge)

    assert errors == []
    assert len(moments) == 1
    moment = moments[0]
    assert moment.inicio == "00:01:50"
    assert moment.fin == "00:02:40"
    assert moment.desglose.reaccion_chat == 16
    assert moment.desglose.contexto == 20
    assert moment.desglose.novedad == 15
    assert moment.desglose.gancho == 12
    assert moment.puntuacion == 16 + 20 + 15 + 12
    assert moment.categoria == "bug gracioso"
    assert moment.gancho == "Mira esto"
    assert moment.chat.msg_min == 120
    assert moment.chat.multiplicador == 3.2


@pytest.mark.parametrize("reaction_points, expected", [(15.5, 16), (14.5, 15)])
def test_judge_candidates_rounds_reaction_points_half_up(reaction_points, expected):
    candidate = make_candidate(100, 235, reaction_points=reaction_points)
    judge = FakeJudge({100: [make_judgment(110, 160)]})

    moments, _ = judge_candidates([candidate], WIDE_TRANSCRIPT, judge)

    assert moments[0].desglose.reaccion_chat == expected
    assert moments[0].puntuacion == expected + 30


def test_judge_receives_only_the_segments_in_the_window():
    candidate = make_candidate(100, 235)
    segments = make_segments((0, 100), (90, 110), (150, 160), (235, 300), (500, 510))
    judge = FakeJudge({100: [make_judgment(110, 160)]})

    judge_candidates([candidate], segments, judge)

    received_candidate, received_segments = judge.calls[0]
    assert received_candidate == candidate
    assert [(s.start_s, s.end_s) for s in received_segments] == [(90, 110), (150, 160)]


# judge_candidates: deduplication and ordering


def test_overlapping_moments_keep_the_higher_score():
    low = make_candidate(0, 100, reaction_points=10.0)
    high = make_candidate(50, 150, reaction_points=10.0)
    judge = FakeJudge(
        {
            0: [make_judgment(0, 100, context=5)],
            50: [make_judgment(50, 150, context=20)],
        }
    )

    moments, errors = judge_candidates([low, high], WIDE_TRANSCRIPT, judge)

    assert errors == []
    assert [(m.inicio, m.fin) for m in moments] == [("00:00:50", "00:02:30")]


def test_overlapping_moments_with_equal_score_keep_the_earlier_start():
    later = make_candidate(50, 150)
    earlier = make_candidate(0, 100)
    judge = FakeJudge(
        {50: [make_judgment(50, 150)], 0: [make_judgment(0, 100)]},
    )

    moments, _ = judge_candidates([later, earlier], WIDE_TRANSCRIPT, judge)

    assert [(m.inicio, m.fin) for m in moments] == [("00:00:00", "00:01:40")]


def test_touching_moments_are_both_kept():
    first = make_candidate(0, 100)
    second = make_candidate(100, 200)
    judge = FakeJudge({0: [make_judgment(0, 100)], 100: [make_judgment(100, 200)]})

    moments, _ = judge_candidates([first, second], WIDE_TRANSCRIPT, judge)

    assert [(m.inicio, m.fin) for m in moments] == [
        ("00:00:00", "00:01:40"),
        ("00:01:40", "00:03:20"),
    ]


def test_deduplication_is_greedy_from_the_highest_score():
    a = make_candidate(0, 100)
    b = make_candidate(90, 200)
    c = make_candidate(190, 300)
    judge = FakeJudge(
        {
            0: [make_judgment(0, 100, context=25)],
            90: [make_judgment(90, 200, context=15)],
            190: [make_judgment(190, 300, context=5)],
        }
    )

    moments, _ = judge_candidates([b, c, a], WIDE_TRANSCRIPT, judge)

    assert [(m.inicio, m.fin) for m in moments] == [
        ("00:00:00", "00:01:40"),
        ("00:03:10", "00:05:00"),
    ]


def test_result_is_cut_to_five_in_descending_score_order():
    starts = [0, 200, 400, 600, 800, 1000, 1200]
    contexts = [3, 25, 8, 20, 1, 14, 11]
    candidates = [make_candidate(s, s + 100) for s in starts]
    judge = FakeJudge(
        {s: [make_judgment(s, s + 100, context=c)] for s, c in zip(starts, contexts)}
    )

    moments, errors = judge_candidates(candidates, WIDE_TRANSCRIPT, judge)

    assert errors == []
    assert len(moments) == 5
    assert [m.desglose.contexto for m in moments] == [25, 20, 14, 11, 8]
    assert [m.puntuacion for m in moments] == sorted(
        (m.puntuacion for m in moments), reverse=True
    )


def test_final_order_breaks_ties_by_earlier_start():
    starts = [600, 0, 300]
    candidates = [make_candidate(s, s + 100) for s in starts]
    judge = FakeJudge({s: [make_judgment(s, s + 100)] for s in starts})

    moments, _ = judge_candidates(candidates, WIDE_TRANSCRIPT, judge)

    assert [m.inicio for m in moments] == ["00:00:00", "00:05:00", "00:10:00"]


def test_judge_candidates_with_no_candidates_returns_empty_results():
    judge = FakeJudge({})
    assert judge_candidates([], WIDE_TRANSCRIPT, judge) == ([], [])
    assert judge.calls == []


# judge_candidates: failures


def test_out_of_window_judgment_is_retried_once_and_then_accepted():
    candidate = make_candidate(100, 235)
    judge = FakeJudge({100: [make_judgment(50, 160), make_judgment(110, 160)]})

    moments, errors = judge_candidates([candidate], WIDE_TRANSCRIPT, judge)

    assert len(judge.calls) == 2
    assert errors == []
    assert [(m.inicio, m.fin) for m in moments] == [("00:01:50", "00:02:40")]


def test_persistent_out_of_window_judgment_skips_only_that_candidate():
    bad = make_candidate(100, 235)
    good = make_candidate(500, 600)
    judge = FakeJudge(
        {
            100: [make_judgment(100, 300), make_judgment(100, 300)],
            500: [make_judgment(510, 560)],
        }
    )

    moments, errors = judge_candidates([bad, good], WIDE_TRANSCRIPT, judge)

    assert len(judge.calls_for(100)) == 2
    assert [(m.inicio, m.fin) for m in moments] == [("00:08:30", "00:09:20")]
    assert len(errors) == 1
    assert errors[0].startswith("candidate 00:01:40-00:03:55: ")
    assert "outside the candidate window" in errors[0]


def test_validation_error_is_retried_once():
    candidate = make_candidate(100, 235)
    judge = FakeJudge({100: [validation_error(), make_judgment(110, 160)]})

    moments, errors = judge_candidates([candidate], WIDE_TRANSCRIPT, judge)

    assert len(judge.calls) == 2
    assert errors == []
    assert len(moments) == 1


def test_persistent_validation_error_is_logged_on_one_line():
    candidate = make_candidate(100, 235)
    judge = FakeJudge({100: [validation_error(), validation_error()]})

    moments, errors = judge_candidates([candidate], WIDE_TRANSCRIPT, judge)

    assert len(judge.calls) == 2
    assert moments == []
    assert len(errors) == 1
    assert errors[0].startswith("candidate 00:01:40-00:03:55: ")
    assert "\n" not in errors[0]


def test_judge_error_twice_skips_the_candidate_and_continues():
    failing = make_candidate(100, 235)
    working = make_candidate(500, 600)
    judge = FakeJudge(
        {
            100: [JudgeError("Gemini request failed: quota"), JudgeError("again")],
            500: [make_judgment(510, 560)],
        }
    )

    moments, errors = judge_candidates([failing, working], WIDE_TRANSCRIPT, judge)

    assert len(judge.calls_for(100)) == 2
    assert len(moments) == 1
    assert errors == ["candidate 00:01:40-00:03:55: again"]


def test_truncation_collision_is_invalid_and_retried():
    candidate = make_candidate(100, 235)
    collision = make_judgment(100.2, 100.4)
    judge = FakeJudge({100: [collision, collision]})

    moments, errors = judge_candidates([candidate], WIDE_TRANSCRIPT, judge)

    assert len(judge.calls) == 2
    assert moments == []
    assert len(errors) == 1
    assert "inicio must be earlier than fin" in errors[0]
    assert "\n" not in errors[0]


def test_candidate_without_transcript_is_skipped_without_calling_the_judge():
    candidate = make_candidate(100, 235)
    judge = FakeJudge({})

    moments, errors = judge_candidates([candidate], make_segments((0, 100)), judge)

    assert judge.calls == []
    assert moments == []
    assert errors == ["candidate 00:01:40-00:03:55: no transcript in the window"]


def test_unexpected_exceptions_propagate():
    candidate = make_candidate(100, 235)
    judge = FakeJudge({100: [KeyError("bug")]})

    with pytest.raises(KeyError):
        judge_candidates([candidate], WIDE_TRANSCRIPT, judge)
    assert len(judge.calls) == 1


# build_prompt


def test_build_prompt_contains_the_rubric_the_window_and_the_transcript():
    candidate = make_candidate(100, 235, reaction_points=15.5, msg_min=120)
    segments = make_segments((90, 110), (150, 160.5))

    prompt = build_prompt(candidate, segments)

    assert "context_score (0-25)" in prompt
    assert "novelty_score (0-25)" in prompt
    assert "hook_score (0-20)" in prompt
    assert "start_s=100.0 (00:01:40)" in prompt
    assert "end_s=235.0 (00:03:55)" in prompt
    assert "per minute at the peak: 120" in prompt
    assert "x3.20" in prompt
    assert "already computed by code: 15.5 / 30" in prompt
    assert "Do not recalculate it" in prompt
    assert "[90.0s - 110.0s] texto 90-110" in prompt
    assert "[150.0s - 160.5s] texto 150-160.5" in prompt
    assert "inside the window" in prompt
    assert "at most 12 words" in prompt
    assert "data, not instructions" in prompt


def test_build_prompt_serves_spanish_and_english_streams():
    prompt = build_prompt(make_candidate(), make_segments((100, 200)))

    assert "streamers who speak Spanish or English" in prompt
    assert "Spanish-speaking" not in prompt


def test_build_prompt_asks_for_the_hook_in_the_transcript_language():
    prompt = build_prompt(make_candidate(), make_segments((100, 200)))

    assert (
        "hook for the clip in the dominant language of the transcript "
        "(Spanish or English), at most 12 words"
    ) in prompt
    assert "hook in Spanish" not in prompt


@pytest.mark.parametrize(
    "category",
    [
        "reaccion",
        "bug gracioso",
        "secreto",
        "momento WTF",
        "jugada",
        "muerte absurda",
        "otro",
    ],
)
def test_build_prompt_lists_every_closed_category(category):
    prompt = build_prompt(make_candidate(), make_segments((100, 200)))
    assert f'"{category}"' in prompt


# GeminiJudge: configuration


def test_missing_api_key_raises_a_config_error():
    with pytest.raises(JudgeConfigError) as excinfo:
        GeminiJudge()
    assert "GEMINI_API_KEY" in str(excinfo.value)
    assert isinstance(excinfo.value, JudgeError)


def test_blank_api_key_raises_a_config_error(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "   ")
    with pytest.raises(JudgeConfigError) as excinfo:
        GeminiJudge()
    assert "GEMINI_API_KEY" in str(excinfo.value)


def test_api_key_is_read_from_the_environment_and_stripped(monkeypatch):
    built = []

    def recording_client(**kwargs):
        built.append(kwargs)
        return FakeClient()

    monkeypatch.setattr(judge_module.genai, "Client", recording_client)
    monkeypatch.setenv("GEMINI_API_KEY", "  fake-key  ")

    GeminiJudge()

    assert built == [{"api_key": "fake-key"}]


def test_injected_client_needs_no_api_key():
    judge = GeminiJudge(client=FakeClient())
    assert judge.model == DEFAULT_GEMINI_MODEL


def test_model_defaults_when_the_variable_is_unset():
    assert GeminiJudge(client=FakeClient()).model == "gemini-3.5-flash-lite"


def test_model_defaults_when_the_variable_is_blank(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "   ")
    assert GeminiJudge(client=FakeClient()).model == DEFAULT_GEMINI_MODEL


def test_model_is_read_from_the_environment(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", " env-model ")
    assert GeminiJudge(client=FakeClient()).model == "env-model"


def test_explicit_model_wins_over_the_environment(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "env-model")
    assert GeminiJudge(client=FakeClient(), model="arg-model").model == "arg-model"


# GeminiJudge: requests and responses


def test_request_carries_model_prompt_and_json_schema_config():
    client = FakeClient(make_response(judgment_json()))
    judge = GeminiJudge(client=client, model="test-model")
    candidate = make_candidate(100, 235, reaction_points=15.5)
    segments = make_segments((90, 110), (150, 160))

    judge.judge(candidate, segments)

    (request,) = client.models.requests
    assert request["model"] == "test-model"
    assert request["contents"] == build_prompt(candidate, segments)
    assert "context_score (0-25)" in request["contents"]
    assert "texto 90-110" in request["contents"]
    assert request["config"].response_mime_type == "application/json"
    assert request["config"].response_json_schema == Judgment.model_json_schema()


def test_response_is_validated_as_a_judgment():
    expected = make_judgment(110.9, 160.7, 20, 15, 12, category="bug gracioso")
    client = FakeClient(make_response(judgment_json(hook="Mira esto")))
    judge = GeminiJudge(client=client)

    result = judge.judge(make_candidate(), make_segments((100, 200)))

    assert result == expected


@pytest.mark.parametrize(
    "text",
    [
        "not json at all",
        '{"start_s": 1, "end_s": 2}',
        judgment_json(category="meme"),
        judgment_json(context_score=99),
    ],
)
def test_invalid_response_raises_a_validation_error(text):
    judge = GeminiJudge(client=FakeClient(make_response(text)))
    with pytest.raises(ValidationError):
        judge.judge(make_candidate(), make_segments((100, 200)))


@pytest.mark.parametrize("text", ["", None])
def test_empty_response_text_raises_a_judge_error(text):
    judge = GeminiJudge(client=FakeClient(make_response(text)))
    with pytest.raises(JudgeError, match="empty response"):
        judge.judge(make_candidate(), make_segments((100, 200)))


def test_sdk_exception_is_wrapped_and_still_counted():
    judge = GeminiJudge(client=FakeClient(RuntimeError("429 quota exhausted")))

    with pytest.raises(JudgeError, match="429 quota exhausted") as excinfo:
        judge.judge(make_candidate(), make_segments((100, 200)))

    assert isinstance(excinfo.value.__cause__, RuntimeError)
    assert judge.calls == 1
    assert judge.input_tokens == 0
    assert judge.output_tokens == 0


# GeminiJudge: counters


def test_counters_start_at_zero():
    judge = GeminiJudge(client=FakeClient())
    assert (judge.calls, judge.input_tokens, judge.output_tokens) == (0, 0, 0)


def test_counters_accumulate_across_calls():
    judge, _, _ = make_paced_judge(
        make_response(
            judgment_json(), make_usage(prompt=1000, candidates=60, thoughts=40)
        ),
        make_response(
            judgment_json(), make_usage(prompt=500, candidates=30, thoughts=None)
        ),
    )
    candidate = make_candidate()
    segments = make_segments((100, 200))

    judge.judge(candidate, segments)
    assert (judge.calls, judge.input_tokens, judge.output_tokens) == (1, 1000, 100)

    judge.judge(candidate, segments)
    assert (judge.calls, judge.input_tokens, judge.output_tokens) == (2, 1500, 130)


def test_missing_usage_metadata_counts_only_the_call():
    judge = GeminiJudge(client=FakeClient(make_response(judgment_json(), usage=None)))

    judge.judge(make_candidate(), make_segments((100, 200)))

    assert (judge.calls, judge.input_tokens, judge.output_tokens) == (1, 0, 0)


# GeminiJudge inside judge_candidates


def test_gemini_judge_end_to_end_with_judge_candidates():
    client = FakeClient(
        make_response(
            judgment_json(), make_usage(prompt=800, candidates=50, thoughts=25)
        )
    )
    judge = GeminiJudge(client=client)
    candidate = make_candidate(100, 235, reaction_points=15.5)

    moments, errors = judge_candidates([candidate], WIDE_TRANSCRIPT, judge)

    assert errors == []
    (moment,) = moments
    assert (moment.inicio, moment.fin) == ("00:01:50", "00:02:40")
    assert moment.desglose.reaccion_chat == 16
    assert moment.puntuacion == 16 + 20 + 15 + 12
    assert moment.categoria == "bug gracioso"
    assert (judge.calls, judge.input_tokens, judge.output_tokens) == (1, 800, 75)


def test_api_error_then_success_counts_two_calls():
    judge, _, _ = make_paced_judge(
        unavailable_error(),
        make_response(judgment_json(), make_usage(prompt=700, candidates=40)),
    )

    moments, errors = judge_candidates(
        [make_candidate(100, 235)], WIDE_TRANSCRIPT, judge
    )

    assert errors == []
    assert len(moments) == 1
    assert (judge.calls, judge.input_tokens, judge.output_tokens) == (2, 700, 40)


# GeminiJudge: pacing


def call(judge):
    return judge.judge(make_candidate(), make_segments((100, 200)))


def ok(**usage):
    return make_response(judgment_json(), make_usage(**usage) if usage else None)


def test_pacing_constants_follow_d16():
    assert MIN_CALL_INTERVAL_S == 12
    assert MAX_TRANSIENT_ATTEMPTS == 3
    assert TRANSIENT_BACKOFF_S == (15, 30)
    assert len(TRANSIENT_BACKOFF_S) == MAX_TRANSIENT_ATTEMPTS - 1
    assert MAX_RETRY_DELAY_S == 300


def test_first_call_does_not_wait():
    judge, _, clock = make_paced_judge(ok())

    call(judge)

    assert clock.sleeps == []


def test_second_call_waits_the_remainder_of_the_interval():
    judge, client, clock = make_paced_judge(ok(), ok())

    call(judge)
    clock.now += 5
    call(judge)

    assert clock.sleeps == [7.0]
    assert client.models.call_times[1] - client.models.call_times[0] == 12


def test_second_call_does_not_wait_when_the_interval_has_passed():
    judge, _, clock = make_paced_judge(ok(), ok())

    call(judge)
    clock.now += 12
    call(judge)

    assert clock.sleeps == []


def test_back_to_back_calls_wait_the_full_interval():
    judge, _, clock = make_paced_judge(ok(), ok(), ok())

    for _ in range(3):
        call(judge)

    assert clock.sleeps == [12.0, 12.0]


def test_interval_is_measured_from_the_start_of_the_previous_call():
    clock = FakeClock()

    class SlowModels(FakeModels):
        def generate_content(self, **kwargs):
            clock.now += 4
            return super().generate_content(**kwargs)

    client = FakeClient()
    client.models = SlowModels([ok(), ok()], clock)
    judge = GeminiJudge(client=client, clock=clock, sleeper=clock.sleep)

    call(judge)
    call(judge)

    assert clock.sleeps == [8.0]


def test_a_validation_retry_is_paced_like_any_other_call():
    judge, client, clock = make_paced_judge(
        make_response("not json"), make_response(judgment_json())
    )

    moments, errors = judge_candidates(
        [make_candidate(100, 235)], WIDE_TRANSCRIPT, judge
    )

    assert errors == []
    assert len(moments) == 1
    assert clock.sleeps == [12.0]
    assert client.models.call_times == [1000.0, 1012.0]


def test_every_call_of_a_whole_run_keeps_the_minimum_interval():
    candidates = [make_candidate(s, s + 100) for s in range(0, 2000, 200)]
    responses = [
        make_response(judgment_json(start_s=s + 10, end_s=s + 60))
        for s in range(0, 2000, 200)
    ]
    judge, client, _ = make_paced_judge(*responses)

    moments, errors = judge_candidates(candidates, WIDE_TRANSCRIPT, judge)

    assert errors == []
    assert len(moments) == 5
    times = client.models.call_times
    assert len(times) == 10
    assert all(later - earlier >= 12 for earlier, later in itertools.pairwise(times))


def test_default_clock_and_sleeper_are_the_real_ones():
    judge = GeminiJudge(client=FakeClient())

    assert judge._clock is judge_module.time.monotonic
    assert judge._sleep is judge_module.time.sleep


# GeminiJudge: transient errors


def test_rate_limit_waits_the_server_retry_delay_and_retries():
    judge, client, clock = make_paced_judge(
        rate_limit_error("37s"), ok(prompt=700, candidates=40)
    )

    result = call(judge)

    assert result.hook == "El coche vuela"
    assert clock.sleeps == [37.0]
    assert len(client.models.requests) == 2
    assert (judge.calls, judge.input_tokens, judge.output_tokens) == (2, 700, 40)


def test_rate_limit_accepts_a_fractional_retry_delay():
    judge, _, clock = make_paced_judge(rate_limit_error("37.5s"), ok())

    call(judge)

    assert clock.sleeps == [37.5]


def test_a_short_retry_delay_is_raised_to_the_minimum_interval():
    judge, client, clock = make_paced_judge(rate_limit_error("2s"), ok())

    call(judge)

    assert clock.sleeps == [12.0]
    assert client.models.call_times == [1000.0, 1012.0]


@pytest.mark.parametrize("retry_delay", [None, "soon", "-5s", "5", "5m", ""])
def test_rate_limit_without_a_usable_retry_delay_uses_the_backoff(retry_delay):
    judge, _, clock = make_paced_judge(rate_limit_error(retry_delay), ok())

    call(judge)

    assert clock.sleeps == [15.0]


def test_service_unavailable_backs_off_15_then_30_seconds():
    judge, client, clock = make_paced_judge(
        unavailable_error(), unavailable_error(), ok()
    )

    call(judge)

    assert clock.sleeps == [15.0, 30.0]
    assert len(client.models.requests) == 3
    assert judge.calls == 3


def test_service_unavailable_ignores_a_retry_delay_in_the_payload():
    error = api_error(503, "99s", "UNAVAILABLE")
    judge, _, clock = make_paced_judge(error, ok())

    call(judge)

    assert clock.sleeps == [15.0]


class TransportError(Exception):
    pass


@pytest.mark.parametrize(
    "error",
    [
        ConnectionError("connection reset"),
        TimeoutError("timed out"),
        OSError("network unreachable"),
        TransportError("httpx style transport failure"),
    ],
)
def test_network_errors_are_transient(error):
    judge, _, clock = make_paced_judge(error, ok())

    call(judge)

    assert clock.sleeps == [15.0]
    assert judge.calls == 2
    assert judge.transient_errors == {"network": 1}


def test_three_transient_failures_give_up_with_a_transient_judge_error():
    last = unavailable_error()
    judge, client, clock = make_paced_judge(
        unavailable_error(), unavailable_error(), last
    )

    with pytest.raises(TransientJudgeError, match="after 3 attempts") as excinfo:
        call(judge)

    assert isinstance(excinfo.value, JudgeError)
    assert excinfo.value.__cause__ is last
    assert clock.sleeps == [15.0, 30.0]
    assert len(client.models.requests) == 3
    assert (judge.calls, judge.input_tokens, judge.output_tokens) == (3, 0, 0)


@pytest.mark.parametrize("code", [400, 401, 403, 404, 500])
def test_other_http_errors_are_not_transient(code):
    judge, client, clock = make_paced_judge(api_error(code))

    with pytest.raises(JudgeError, match=f"{code}") as excinfo:
        call(judge)

    assert not isinstance(excinfo.value, TransientJudgeError)
    assert clock.sleeps == []
    assert len(client.models.requests) == 1
    assert judge.retries == 0
    assert judge.transient_errors == {}


def test_a_plain_exception_is_not_transient():
    judge, _, clock = make_paced_judge(RuntimeError("boom"))

    with pytest.raises(JudgeError, match="boom") as excinfo:
        call(judge)

    assert not isinstance(excinfo.value, TransientJudgeError)
    assert clock.sleeps == []
    assert judge.calls == 1


def test_validation_errors_are_never_retried_inside_the_judge():
    judge, client, clock = make_paced_judge(make_response("not json"))

    with pytest.raises(ValidationError):
        call(judge)

    assert clock.sleeps == []
    assert len(client.models.requests) == 1


def test_empty_response_is_not_retried_inside_the_judge():
    judge, client, _ = make_paced_judge(make_response(""))

    with pytest.raises(JudgeError, match="empty response"):
        call(judge)

    assert len(client.models.requests) == 1


def test_retries_and_transient_error_counters():
    judge, _, _ = make_paced_judge(
        rate_limit_error("20s"), unavailable_error(), rate_limit_error(), ok()
    )

    with pytest.raises(TransientJudgeError):
        call(judge)
    assert (judge.calls, judge.retries) == (3, 2)
    assert judge.transient_errors == {"429": 2, "503": 1}


def test_counters_start_without_retries_or_transient_errors():
    judge = GeminiJudge(client=FakeClient())
    assert judge.retries == 0
    assert judge.transient_errors == {}


def test_transient_attempts_are_counted_per_judge_call():
    judge, client, _ = make_paced_judge(
        unavailable_error(), unavailable_error(), unavailable_error(), ok()
    )

    with pytest.raises(TransientJudgeError):
        call(judge)
    other = make_candidate(500, 600)
    judge.judge(other, make_segments((500, 600)))

    assert len(client.models.requests) == 4


# GeminiJudge inside judge_candidates: transient errors


def test_exhausted_transient_errors_cost_exactly_three_calls_end_to_end():
    failing = make_candidate(100, 235)
    working = make_candidate(500, 600)
    judge, client, _ = make_paced_judge(
        unavailable_error(),
        unavailable_error(),
        unavailable_error(),
        make_response(judgment_json(start_s=510, end_s=560)),
    )

    moments, errors = judge_candidates([failing, working], WIDE_TRANSCRIPT, judge)

    assert len(client.models.requests) == 4
    assert judge.calls == 4
    assert [(m.inicio, m.fin) for m in moments] == [("00:08:30", "00:09:20")]
    assert len(errors) == 1
    assert errors[0].startswith("candidate 00:01:40-00:03:55: ")
    assert "after 3 attempts" in errors[0]
    assert "\n" not in errors[0]


def test_the_judge_keeps_no_memory_of_a_candidate_it_gave_up_on():
    candidate = make_candidate(100, 235)
    segments = make_segments((100, 200))
    judge, client, _ = make_paced_judge(
        unavailable_error(), unavailable_error(), unavailable_error(), ok()
    )

    with pytest.raises(TransientJudgeError):
        judge.judge(candidate, segments)
    result = judge.judge(candidate, segments)

    assert result.hook == "El coche vuela"
    assert len(client.models.requests) == 4


def test_judge_candidates_does_not_retry_a_transient_judge_error():
    failing = make_candidate(100, 235)
    judge = FakeJudge(
        {100: [TransientJudgeError("after 3 attempts"), make_judgment(110, 160)]}
    )

    moments, errors = judge_candidates([failing], WIDE_TRANSCRIPT, judge)

    assert len(judge.calls_for(100)) == 1
    assert moments == []
    assert errors == ["candidate 00:01:40-00:03:55: after 3 attempts"]


def test_rate_limit_inside_a_run_is_retried_and_the_candidate_is_kept():
    judge, _, clock = make_paced_judge(
        rate_limit_error("20s"), ok(prompt=800, candidates=50, thoughts=25)
    )

    moments, errors = judge_candidates(
        [make_candidate(100, 235)], WIDE_TRANSCRIPT, judge
    )

    assert errors == []
    assert len(moments) == 1
    assert clock.sleeps == [20.0]
    assert (judge.calls, judge.input_tokens, judge.output_tokens) == (2, 800, 75)
    assert judge.transient_errors == {"429": 1}


def test_validation_error_after_a_transient_retry_still_gets_its_single_retry():
    judge, _, _ = make_paced_judge(
        unavailable_error(),
        make_response("not json"),
        make_response(judgment_json()),
    )

    moments, errors = judge_candidates(
        [make_candidate(100, 235)], WIDE_TRANSCRIPT, judge
    )

    assert errors == []
    assert len(moments) == 1
    assert judge.calls == 3


def test_a_non_transient_failure_keeps_the_single_retry_of_the_caller():
    judge, client, clock = make_paced_judge(api_error(400), api_error(400))

    moments, errors = judge_candidates(
        [make_candidate(100, 235)], WIDE_TRANSCRIPT, judge
    )

    assert moments == []
    assert len(errors) == 1
    assert len(client.models.requests) == 2
    assert clock.sleeps == [12.0]


# GeminiJudge: cap on the server retry delay (D18)


def test_a_retry_delay_at_the_cap_is_waited():
    judge, _, clock = make_paced_judge(rate_limit_error("300s"), ok())

    call(judge)

    assert clock.sleeps == [300.0]
    assert judge.retries == 1


@pytest.mark.parametrize("retry_delay", ["300.5s", "301s", "86400s"])
def test_a_retry_delay_above_the_cap_gives_up_without_waiting(retry_delay):
    judge, client, clock = make_paced_judge(rate_limit_error(retry_delay), ok())

    with pytest.raises(TransientJudgeError) as excinfo:
        call(judge)

    message = str(excinfo.value)
    assert f"retry in {retry_delay[:-1]} s" in message
    assert "above the limit of 300 s" in message
    assert isinstance(excinfo.value.__cause__, genai_errors.ClientError)
    assert clock.sleeps == []
    assert len(client.models.requests) == 1
    assert (judge.calls, judge.retries) == (1, 0)
    assert judge.transient_errors == {"429": 1}


def test_a_capped_retry_delay_costs_one_call_through_judge_candidates():
    judge, client, clock = make_paced_judge(rate_limit_error("3600s"), ok())

    moments, errors = judge_candidates(
        [make_candidate(100, 235)], WIDE_TRANSCRIPT, judge
    )

    assert moments == []
    assert len(errors) == 1
    assert "retry in 3600 s, above the limit of 300 s" in errors[0]
    assert len(client.models.requests) == 1
    assert clock.sleeps == []


def test_a_candidate_that_exhausts_transient_errors_costs_three_calls_not_six():
    judge, client, clock = make_paced_judge(*[unavailable_error() for _ in range(6)])

    moments, errors = judge_candidates(
        [make_candidate(100, 235)], WIDE_TRANSCRIPT, judge
    )

    assert moments == []
    assert len(errors) == 1
    assert len(client.models.requests) == 3
    assert judge.calls == 3
    assert clock.sleeps == [15.0, 30.0]
