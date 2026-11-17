import math
import re

_HHMMSS = re.compile(r"([0-9]{2,}):([0-5][0-9]):([0-5][0-9])")


class TiempoInvalido(ValueError):
    pass


def hhmmss_a_segundos(texto: str) -> int:
    coincidencia = _HHMMSS.fullmatch(texto)
    if coincidencia is None:
        raise TiempoInvalido(
            f"se esperaba HH:MM:SS (horas con dos cifras o más), llegó {texto!r}"
        )
    horas, minutos, segundos = (int(grupo) for grupo in coincidencia.groups())
    return horas * 3600 + minutos * 60 + segundos


def parsear_tiempo(valor: object) -> float:
    if isinstance(valor, bool) or valor is None:
        raise TiempoInvalido(f"se esperaba segundos o HH:MM:SS, llegó {valor!r}")

    if isinstance(valor, (int, float)):
        segundos = float(valor)
    elif isinstance(valor, str):
        texto = valor.strip()
        if ":" in texto:
            return float(hhmmss_a_segundos(texto))
        try:
            segundos = float(texto)
        except ValueError:
            raise TiempoInvalido(
                f"se esperaba segundos o HH:MM:SS, llegó {valor!r}"
            ) from None
    else:
        raise TiempoInvalido(
            f"se esperaba segundos o HH:MM:SS, llegó {type(valor).__name__}"
        )

    if not math.isfinite(segundos) or segundos < 0:
        raise TiempoInvalido(
            f"el tiempo debe ser finito y no negativo, llegó {valor!r}"
        )
    return segundos
