import csv
import json
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

from pydantic import ValidationError

from src.models import ChatEvent, Segment
from src.tiempo import parsear_tiempo

T = TypeVar("T", ChatEvent, Segment)

CLAVES_TRANSCRIPCION = ("start_s", "end_s", "text")
CLAVES_CHAT = ("t_s", "message")


class ErrorDeCarga(ValueError):
    pass


def cargar_transcripcion(ruta: str | Path) -> list[Segment]:
    return _cargar(ruta, CLAVES_TRANSCRIPCION, ("start_s", "end_s"), Segment)


def cargar_chat(ruta: str | Path) -> list[ChatEvent]:
    return _cargar(ruta, CLAVES_CHAT, ("t_s",), ChatEvent)


def _cargar(
    ruta: str | Path,
    claves: tuple[str, ...],
    claves_de_tiempo: tuple[str, ...],
    modelo: Callable[..., T],
) -> list[T]:
    ruta = Path(ruta)
    registros = _leer_registros(ruta)
    return [
        _construir(ruta, numero, registro, claves, claves_de_tiempo, modelo)
        for numero, registro in enumerate(registros, start=1)
    ]


def _leer_registros(ruta: Path) -> list[dict]:
    if not ruta.is_file():
        raise ErrorDeCarga(f"{ruta}: el fichero no existe")

    extension = ruta.suffix.lower()
    if extension == ".json":
        return _leer_json(ruta)
    if extension == ".csv":
        return _leer_csv(ruta)
    raise ErrorDeCarga(
        f"{ruta.name}: formato no soportado ({ruta.suffix!r}); usa .json o .csv"
    )


def _leer_json(ruta: Path) -> list[dict]:
    try:
        contenido = json.loads(ruta.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as error:
        raise ErrorDeCarga(f"{ruta.name}: JSON no válido ({error})") from error

    if not isinstance(contenido, list):
        raise ErrorDeCarga(
            f"{ruta.name}: se esperaba una lista de objetos en la raíz del JSON"
        )
    for numero, registro in enumerate(contenido, start=1):
        if not isinstance(registro, dict):
            raise ErrorDeCarga(f"{ruta.name}, registro {numero}: se esperaba un objeto")
    return contenido


def _leer_csv(ruta: Path) -> list[dict]:
    with ruta.open(encoding="utf-8-sig", newline="") as fichero:
        lector = csv.DictReader(fichero)
        if lector.fieldnames is None:
            raise ErrorDeCarga(
                f"{ruta.name}: el CSV está vacío; falta la fila de cabecera"
            )
        registros = []
        for numero, fila in enumerate(lector, start=1):
            if None in fila:
                raise ErrorDeCarga(
                    f"{ruta.name}, registro {numero}: más columnas que la cabecera"
                )
            registros.append(fila)
    return registros


def _construir(
    ruta: Path,
    numero: int,
    registro: dict,
    claves: tuple[str, ...],
    claves_de_tiempo: tuple[str, ...],
    modelo: Callable[..., T],
) -> T:
    donde = f"{ruta.name}, registro {numero}"

    faltan = [clave for clave in claves if clave not in registro]
    if faltan:
        raise ErrorDeCarga(
            f"{donde}: faltan las claves {', '.join(faltan)}; se esperaba "
            f"{', '.join(claves)} y llegó {', '.join(str(clave) for clave in registro) or 'nada'}"
        )

    datos = {clave: registro[clave] for clave in claves}
    for clave in claves_de_tiempo:
        try:
            datos[clave] = parsear_tiempo(datos[clave])
        except ValueError as error:
            raise ErrorDeCarga(f"{donde}, clave {clave}: {error}") from error

    try:
        return modelo(**datos)
    except ValidationError as error:
        detalle = "; ".join(
            f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in error.errors()
        )
        raise ErrorDeCarga(f"{donde}: {detalle}") from error
