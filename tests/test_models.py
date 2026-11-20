import pytest
from pydantic import ValidationError

from src.models import (
    Breakdown,
    Candidate,
    Chat,
    ChatEvent,
    Moment,
    ReferenceClip,
    Segment,
)

CATEGORIES = [
    "reaccion",
    "bug gracioso",
    "secreto",
    "momento WTF",
    "jugada",
    "muerte absurda",
    "otro",
]


def valid_moment(**changes):
    data = {
        "inicio": "01:23:45",
        "fin": "01:24:30",
        "puntuacion": 87,
        "desglose": {"reaccion_chat": 28, "contexto": 22, "novedad": 20, "gancho": 17},
        "categoria": "bug gracioso",
        "gancho": "Proposed hook text for the clip",
        "chat": {"msg_min": 142.0, "multiplicador": 4.7},
    }
    data.update(changes)
    return data


def test_segment_valid():
    segment = Segment(start_s=1.5, end_s=4, text="hello")
    assert (segment.start_s, segment.end_s, segment.text) == (1.5, 4.0, "hello")


def test_segment_rejects_end_equal_to_start():
    with pytest.raises(ValidationError, match="end_s must be greater than start_s"):
        Segment(start_s=3, end_s=3, text="x")


@pytest.mark.parametrize(
    "data",
    [
        {"start_s": 5, "end_s": 4, "text": "x"},
        {"start_s": 3, "end_s": 3, "text": "x"},
        {"start_s": -1, "end_s": 4, "text": "x"},
        {"start_s": 0, "end_s": -1, "text": "x"},
        {"start_s": float("nan"), "end_s": 4, "text": "x"},
        {"start_s": 0, "end_s": float("inf"), "text": "x"},
        {"start_s": 0, "end_s": 4},
        {"start_s": 0, "end_s": 4, "text": "x", "extra": 1},
    ],
)
def test_segment_invalid(data):
    with pytest.raises(ValidationError):
        Segment(**data)


def test_chat_event_valid():
    event = ChatEvent(t_s=3725, message="lol")
    assert (event.t_s, event.message) == (3725.0, "lol")


@pytest.mark.parametrize(
    "data",
    [
        {"t_s": -1, "message": "x"},
        {"t_s": float("nan"), "message": "x"},
        {"t_s": 1},
        {"t_s": 1, "message": "x", "extra": 1},
    ],
)
def test_chat_event_invalid(data):
    with pytest.raises(ValidationError):
        ChatEvent(**data)


@pytest.mark.parametrize(
    ("field", "maximum"),
    [("reaccion_chat", 30), ("contexto", 25), ("novedad", 25), ("gancho", 20)],
)
def test_breakdown_enforces_each_field_range(field, maximum):
    base = {"reaccion_chat": 0, "contexto": 0, "novedad": 0, "gancho": 0}
    assert getattr(Breakdown(**{**base, field: maximum}), field) == maximum
    with pytest.raises(ValidationError):
        Breakdown(**{**base, field: maximum + 1})
    with pytest.raises(ValidationError):
        Breakdown(**{**base, field: -1})


def test_breakdown_total_sums_the_four_fields():
    breakdown = Breakdown(reaccion_chat=28, contexto=22, novedad=20, gancho=17)
    assert breakdown.total == 87


def test_breakdown_maximum_totals_one_hundred():
    assert Breakdown(reaccion_chat=30, contexto=25, novedad=25, gancho=20).total == 100


@pytest.mark.parametrize(
    "data",
    [{"msg_min": -1, "multiplicador": 1}, {"msg_min": 1, "multiplicador": -0.1}],
)
def test_chat_rejects_negatives(data):
    with pytest.raises(ValidationError):
        Chat(**data)


def test_chat_accepts_zero():
    assert Chat(msg_min=0, multiplicador=0).multiplicador == 0


def test_moment_valid():
    moment = Moment(**valid_moment())
    assert moment.puntuacion == 87
    assert moment.desglose.total == 87
    assert moment.chat.multiplicador == 4.7


@pytest.mark.parametrize("category", CATEGORIES)
def test_moment_accepts_each_closed_category(category):
    assert Moment(**valid_moment(categoria=category)).categoria == category


@pytest.mark.parametrize("category", ["Reaccion", "gracioso", "", "otro "])
def test_moment_rejects_category_outside_the_list(category):
    with pytest.raises(ValidationError):
        Moment(**valid_moment(categoria=category))


@pytest.mark.parametrize(
    "time", ["1:23:45", "01:23", "01:60:00", "01:23:45\n", "abc", ""]
)
def test_moment_rejects_malformed_times(time):
    with pytest.raises(ValidationError):
        Moment(**valid_moment(inicio=time))


@pytest.mark.parametrize(
    ("inicio", "fin"),
    [("01:24:30", "01:24:30"), ("01:25:00", "01:24:30")],
)
def test_moment_requires_inicio_before_fin(inicio, fin):
    with pytest.raises(ValidationError, match="inicio must be earlier than fin"):
        Moment(**valid_moment(inicio=inicio, fin=fin))


def test_moment_requires_puntuacion_to_equal_the_breakdown_sum():
    with pytest.raises(ValidationError, match="does not match the sum"):
        Moment(**valid_moment(puntuacion=88))


@pytest.mark.parametrize("score", [-1, 101])
def test_moment_rejects_score_out_of_range(score):
    with pytest.raises(ValidationError):
        Moment(**valid_moment(puntuacion=score))


def test_moment_rejects_empty_hook():
    with pytest.raises(ValidationError):
        Moment(**valid_moment(gancho="   "))


def test_moment_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        Moment(**valid_moment(extra="x"))


def test_moment_serializes_with_the_spec_shape():
    output = Moment(**valid_moment()).model_dump()
    assert set(output) == {
        "inicio",
        "fin",
        "puntuacion",
        "desglose",
        "categoria",
        "gancho",
        "chat",
    }
    assert set(output["desglose"]) == {"reaccion_chat", "contexto", "novedad", "gancho"}
    assert set(output["chat"]) == {"msg_min", "multiplicador"}


def valid_candidate(**changes):
    data = {
        "start_s": 240,
        "end_s": 375,
        "msg_min": 40,
        "multiplier": 4.0,
        "reaction_points": 28.0,
    }
    data.update(changes)
    return data


def test_candidate_valid():
    candidate = Candidate(**valid_candidate())
    assert (candidate.start_s, candidate.end_s, candidate.msg_min) == (240.0, 375.0, 40)


@pytest.mark.parametrize("points", [0, 15.5, 30])
def test_candidate_accepts_points_within_range(points):
    assert (
        Candidate(**valid_candidate(reaction_points=points)).reaction_points == points
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"end_s": 240},
        {"end_s": 100},
        {"start_s": -1},
        {"msg_min": -1},
        {"msg_min": 1.5},
        {"multiplier": -0.1},
        {"reaction_points": -0.1},
        {"reaction_points": 30.1},
        {"reaction_points": float("nan")},
        {"extra": 1},
    ],
)
def test_candidate_invalid(changes):
    with pytest.raises(ValidationError):
        Candidate(**valid_candidate(**changes))


def test_reference_clip_valid():
    clip = ReferenceClip(start_s=610, end_s=640.5)
    assert (clip.start_s, clip.end_s) == (610.0, 640.5)


def test_reference_clip_rejects_end_equal_to_start():
    with pytest.raises(ValidationError, match="end_s must be greater than start_s"):
        ReferenceClip(start_s=3, end_s=3)


@pytest.mark.parametrize(
    "data",
    [
        {"start_s": 5, "end_s": 4},
        {"start_s": -1, "end_s": 4},
        {"start_s": 0, "end_s": -1},
        {"start_s": float("nan"), "end_s": 4},
        {"start_s": 0, "end_s": float("inf")},
        {"start_s": 0},
        {"end_s": 4},
        {"start_s": 0, "end_s": 4, "title": "x"},
    ],
)
def test_reference_clip_invalid(data):
    with pytest.raises(ValidationError):
        ReferenceClip(**data)
