from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from src.timeparse import hhmmss_to_seconds

Category = Literal[
    "reaccion",
    "bug gracioso",
    "secreto",
    "momento WTF",
    "jugada",
    "muerte absurda",
    "otro",
]

Seconds = Annotated[float, Field(ge=0, allow_inf_nan=False)]
NonNegative = Annotated[float, Field(ge=0, allow_inf_nan=False)]
ClockTime = Annotated[
    str, StringConstraints(pattern=r"^[0-9]{2,}:[0-5][0-9]:[0-5][0-9]$")
]
NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Segment(_Model):
    start_s: Seconds
    end_s: Seconds
    text: str

    @model_validator(mode="after")
    def _end_after_start(self) -> "Segment":
        if self.end_s <= self.start_s:
            raise ValueError("end_s must be greater than start_s")
        return self


class ChatEvent(_Model):
    t_s: Seconds
    message: str


class Breakdown(_Model):
    reaccion_chat: int = Field(ge=0, le=30)
    contexto: int = Field(ge=0, le=25)
    novedad: int = Field(ge=0, le=25)
    gancho: int = Field(ge=0, le=20)

    @property
    def total(self) -> int:
        return self.reaccion_chat + self.contexto + self.novedad + self.gancho


class Chat(_Model):
    msg_min: NonNegative
    multiplicador: NonNegative


class Moment(_Model):
    inicio: ClockTime
    fin: ClockTime
    puntuacion: int = Field(ge=0, le=100)
    desglose: Breakdown
    categoria: Category
    gancho: NonEmptyText
    chat: Chat

    @model_validator(mode="after")
    def _consistent(self) -> "Moment":
        if hhmmss_to_seconds(self.inicio) >= hhmmss_to_seconds(self.fin):
            raise ValueError("inicio must be earlier than fin")
        if self.puntuacion != self.desglose.total:
            raise ValueError(
                f"puntuacion ({self.puntuacion}) does not match the sum of "
                f"desglose ({self.desglose.total})"
            )
        return self
