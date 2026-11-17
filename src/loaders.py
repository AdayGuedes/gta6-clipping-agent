import csv
import json
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

from pydantic import ValidationError

from src.models import ChatEvent, Segment
from src.timeparse import parse_time

T = TypeVar("T", ChatEvent, Segment)

TRANSCRIPT_KEYS = ("start_s", "end_s", "text")
CHAT_KEYS = ("t_s", "message")


class LoadError(ValueError):
    pass


def load_transcript(path: str | Path) -> list[Segment]:
    return _load(path, TRANSCRIPT_KEYS, ("start_s", "end_s"), Segment)


def load_chat(path: str | Path) -> list[ChatEvent]:
    return _load(path, CHAT_KEYS, ("t_s",), ChatEvent)


def _load(
    path: str | Path,
    keys: tuple[str, ...],
    time_keys: tuple[str, ...],
    model: Callable[..., T],
) -> list[T]:
    path = Path(path)
    records = _read_records(path)
    return [
        _build(path, number, record, keys, time_keys, model)
        for number, record in enumerate(records, start=1)
    ]


def _read_records(path: Path) -> list[dict]:
    if not path.is_file():
        raise LoadError(f"{path}: file does not exist")

    extension = path.suffix.lower()
    if extension == ".json":
        return _read_json(path)
    if extension == ".csv":
        return _read_csv(path)
    raise LoadError(
        f"{path.name}: unsupported format ({path.suffix!r}); use .json or .csv"
    )


def _read_json(path: Path) -> list[dict]:
    try:
        content = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as error:
        raise LoadError(f"{path.name}: invalid JSON ({error})") from error

    if not isinstance(content, list):
        raise LoadError(f"{path.name}: expected a list of objects at the JSON root")
    for number, record in enumerate(content, start=1):
        if not isinstance(record, dict):
            raise LoadError(f"{path.name}, record {number}: expected an object")
    return content


def _read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames is None:
            raise LoadError(f"{path.name}: the CSV is empty; the header row is missing")
        records = []
        for number, row in enumerate(reader, start=1):
            if None in row:
                raise LoadError(
                    f"{path.name}, record {number}: more columns than the header"
                )
            records.append(row)
    return records


def _build(
    path: Path,
    number: int,
    record: dict,
    keys: tuple[str, ...],
    time_keys: tuple[str, ...],
    model: Callable[..., T],
) -> T:
    where = f"{path.name}, record {number}"

    missing = [key for key in keys if key not in record]
    if missing:
        found = ", ".join(str(key) for key in record) or "nothing"
        raise LoadError(
            f"{where}: missing keys {', '.join(missing)}; "
            f"expected {', '.join(keys)} but got {found}"
        )

    data = {key: record[key] for key in keys}
    for key in time_keys:
        try:
            data[key] = parse_time(data[key])
        except ValueError as error:
            raise LoadError(f"{where}, key {key}: {error}") from error

    try:
        return model(**data)
    except ValidationError as error:
        details = "; ".join(
            f"{'.'.join(map(str, e['loc']))}: {e['msg']}" if e["loc"] else e["msg"]
            for e in error.errors()
        )
        raise LoadError(f"{where}: {details}") from error
