import pytest
from pydantic import ValidationError

from src.models import Chat, ChatEvent, Desglose, Momento, Segment

CATEGORIAS = [
    "reaccion",
    "bug gracioso",
    "secreto",
    "momento WTF",
    "jugada",
    "muerte absurda",
    "otro",
]


def momento_valido(**cambios):
    datos = {
        "inicio": "01:23:45",
        "fin": "01:24:30",
        "puntuacion": 87,
        "desglose": {"reaccion_chat": 28, "contexto": 22, "novedad": 20, "gancho": 17},
        "categoria": "bug gracioso",
        "gancho": "Texto propuesto para el gancho del clip",
        "chat": {"msg_min": 142.0, "multiplicador": 4.7},
    }
    datos.update(cambios)
    return datos


def test_segment_valido():
    segmento = Segment(start_s=1.5, end_s=4, text="hola")
    assert (segmento.start_s, segmento.end_s, segmento.text) == (1.5, 4.0, "hola")


def test_segment_permite_inicio_igual_a_fin():
    assert Segment(start_s=3, end_s=3, text="").end_s == 3


@pytest.mark.parametrize(
    "datos",
    [
        {"start_s": 5, "end_s": 4, "text": "x"},
        {"start_s": -1, "end_s": 4, "text": "x"},
        {"start_s": 0, "end_s": -1, "text": "x"},
        {"start_s": float("nan"), "end_s": 4, "text": "x"},
        {"start_s": 0, "end_s": float("inf"), "text": "x"},
        {"start_s": 0, "end_s": 4},
        {"start_s": 0, "end_s": 4, "text": "x", "extra": 1},
    ],
)
def test_segment_invalido(datos):
    with pytest.raises(ValidationError):
        Segment(**datos)


def test_chat_event_valido():
    evento = ChatEvent(t_s=3725, message="jajaja")
    assert (evento.t_s, evento.message) == (3725.0, "jajaja")


@pytest.mark.parametrize(
    "datos",
    [
        {"t_s": -1, "message": "x"},
        {"t_s": float("nan"), "message": "x"},
        {"t_s": 1},
        {"t_s": 1, "message": "x", "extra": 1},
    ],
)
def test_chat_event_invalido(datos):
    with pytest.raises(ValidationError):
        ChatEvent(**datos)


@pytest.mark.parametrize(
    ("campo", "maximo"),
    [("reaccion_chat", 30), ("contexto", 25), ("novedad", 25), ("gancho", 20)],
)
def test_desglose_respeta_rango_de_cada_campo(campo, maximo):
    base = {"reaccion_chat": 0, "contexto": 0, "novedad": 0, "gancho": 0}
    assert getattr(Desglose(**{**base, campo: maximo}), campo) == maximo
    with pytest.raises(ValidationError):
        Desglose(**{**base, campo: maximo + 1})
    with pytest.raises(ValidationError):
        Desglose(**{**base, campo: -1})


def test_desglose_total_suma_los_cuatro_campos():
    desglose = Desglose(reaccion_chat=28, contexto=22, novedad=20, gancho=17)
    assert desglose.total == 87


def test_desglose_maximo_suma_cien():
    assert Desglose(reaccion_chat=30, contexto=25, novedad=25, gancho=20).total == 100


@pytest.mark.parametrize(
    "datos",
    [{"msg_min": -1, "multiplicador": 1}, {"msg_min": 1, "multiplicador": -0.1}],
)
def test_chat_rechaza_negativos(datos):
    with pytest.raises(ValidationError):
        Chat(**datos)


def test_chat_acepta_cero():
    assert Chat(msg_min=0, multiplicador=0).multiplicador == 0


def test_momento_valido():
    momento = Momento(**momento_valido())
    assert momento.puntuacion == 87
    assert momento.desglose.total == 87
    assert momento.chat.multiplicador == 4.7


@pytest.mark.parametrize("categoria", CATEGORIAS)
def test_momento_acepta_cada_categoria_cerrada(categoria):
    assert Momento(**momento_valido(categoria=categoria)).categoria == categoria


@pytest.mark.parametrize("categoria", ["Reaccion", "gracioso", "", "otro "])
def test_momento_rechaza_categoria_fuera_de_la_lista(categoria):
    with pytest.raises(ValidationError):
        Momento(**momento_valido(categoria=categoria))


@pytest.mark.parametrize(
    "hora", ["1:23:45", "01:23", "01:60:00", "01:23:45\n", "abc", ""]
)
def test_momento_rechaza_horas_mal_formadas(hora):
    with pytest.raises(ValidationError):
        Momento(**momento_valido(inicio=hora))


@pytest.mark.parametrize(
    ("inicio", "fin"),
    [("01:24:30", "01:24:30"), ("01:25:00", "01:24:30")],
)
def test_momento_exige_inicio_anterior_a_fin(inicio, fin):
    with pytest.raises(ValidationError, match="inicio debe ser anterior a fin"):
        Momento(**momento_valido(inicio=inicio, fin=fin))


def test_momento_exige_puntuacion_igual_a_la_suma_del_desglose():
    with pytest.raises(ValidationError, match="no coincide con la suma"):
        Momento(**momento_valido(puntuacion=88))


@pytest.mark.parametrize("puntuacion", [-1, 101])
def test_momento_rechaza_puntuacion_fuera_de_rango(puntuacion):
    with pytest.raises(ValidationError):
        Momento(**momento_valido(puntuacion=puntuacion))


def test_momento_rechaza_gancho_vacio():
    with pytest.raises(ValidationError):
        Momento(**momento_valido(gancho="   "))


def test_momento_rechaza_campos_desconocidos():
    with pytest.raises(ValidationError):
        Momento(**momento_valido(extra="x"))


def test_momento_serializa_con_la_forma_de_la_spec():
    salida = Momento(**momento_valido()).model_dump()
    assert set(salida) == {
        "inicio",
        "fin",
        "puntuacion",
        "desglose",
        "categoria",
        "gancho",
        "chat",
    }
    assert set(salida["desglose"]) == {"reaccion_chat", "contexto", "novedad", "gancho"}
    assert set(salida["chat"]) == {"msg_min", "multiplicador"}
