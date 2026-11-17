from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from src.tiempo import hhmmss_a_segundos

Categoria = Literal[
    "reaccion",
    "bug gracioso",
    "secreto",
    "momento WTF",
    "jugada",
    "muerte absurda",
    "otro",
]

Segundos = Annotated[float, Field(ge=0, allow_inf_nan=False)]
NoNegativo = Annotated[float, Field(ge=0, allow_inf_nan=False)]
HoraHHMMSS = Annotated[
    str, StringConstraints(pattern=r"^[0-9]{2,}:[0-5][0-9]:[0-5][0-9]$")
]
TextoNoVacio = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class _Modelo(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Segment(_Modelo):
    start_s: Segundos
    end_s: Segundos
    text: str

    @model_validator(mode="after")
    def _fin_no_antes_del_inicio(self) -> "Segment":
        if self.end_s < self.start_s:
            raise ValueError("end_s no puede ser menor que start_s")
        return self


class ChatEvent(_Modelo):
    t_s: Segundos
    message: str


class Desglose(_Modelo):
    reaccion_chat: int = Field(ge=0, le=30)
    contexto: int = Field(ge=0, le=25)
    novedad: int = Field(ge=0, le=25)
    gancho: int = Field(ge=0, le=20)

    @property
    def total(self) -> int:
        return self.reaccion_chat + self.contexto + self.novedad + self.gancho


class Chat(_Modelo):
    msg_min: NoNegativo
    multiplicador: NoNegativo


class Momento(_Modelo):
    inicio: HoraHHMMSS
    fin: HoraHHMMSS
    puntuacion: int = Field(ge=0, le=100)
    desglose: Desglose
    categoria: Categoria
    gancho: TextoNoVacio
    chat: Chat

    @model_validator(mode="after")
    def _coherencia(self) -> "Momento":
        if hhmmss_a_segundos(self.inicio) >= hhmmss_a_segundos(self.fin):
            raise ValueError("inicio debe ser anterior a fin")
        if self.puntuacion != self.desglose.total:
            raise ValueError(
                f"puntuacion ({self.puntuacion}) no coincide con la suma del "
                f"desglose ({self.desglose.total})"
            )
        return self
