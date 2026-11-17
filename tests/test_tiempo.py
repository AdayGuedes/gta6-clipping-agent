import pytest

from src.tiempo import hhmmss_a_segundos, parsear_tiempo


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("00:00:00", 0),
        ("00:01:05", 65),
        ("01:23:45", 5025),
        ("100:00:00", 360000),
    ],
)
def test_hhmmss_a_segundos(texto, esperado):
    assert hhmmss_a_segundos(texto) == esperado


@pytest.mark.parametrize(
    "texto", ["0:05:30", "01:60:00", "01:00:60", "1:2:3", "01:23", "", "abc"]
)
def test_hhmmss_rechaza_formatos_invalidos(texto):
    with pytest.raises(ValueError):
        hhmmss_a_segundos(texto)


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        (0, 0.0),
        (65, 65.0),
        (12.5, 12.5),
        ("00:01:05", 65.0),
        ("65", 65.0),
        (" 12.5 ", 12.5),
    ],
)
def test_parsear_tiempo_acepta_numero_y_hhmmss(valor, esperado):
    resultado = parsear_tiempo(valor)
    assert resultado == esperado
    assert isinstance(resultado, float)


@pytest.mark.parametrize(
    "valor",
    [
        -1,
        -0.5,
        "-3",
        float("nan"),
        float("inf"),
        "nan",
        "inf",
        True,
        None,
        [],
        "",
        "no es tiempo",
    ],
)
def test_parsear_tiempo_rechaza_valores_invalidos(valor):
    with pytest.raises(ValueError):
        parsear_tiempo(valor)
