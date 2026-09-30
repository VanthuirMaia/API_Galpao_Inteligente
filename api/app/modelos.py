from datetime import datetime

from pydantic import BaseModel


class DispositivoOut(BaseModel):
    id: str
    ambiente: str
    descricao: str | None
    ativo: bool
    ultima_leitura_em: datetime | None
    online: bool


class LeituraOut(BaseModel):
    ts: datetime
    ts_origem: str
    recebido_em: datetime
    t_int: float
    ur_int: float
    t_globo: float
    t_ext: float | None
    ur_ext: float | None
    tpo: float
    itgu: float
    rssi: int | None


class UltimaOut(BaseModel):
    device_id: str
    leitura: LeituraOut | None


class LeituraAgregadaOut(BaseModel):
    janela: datetime  # início do intervalo
    n: int  # leituras na janela
    t_int: float
    ur_int: float
    t_globo: float
    t_ext: float | None
    ur_ext: float | None
    tpo: float
    itgu: float
    itgu_min: float
    itgu_max: float


class LeiturasOut(BaseModel):
    device_id: str
    inicio: datetime
    fim: datetime
    agregacao: str
    total: int
    itens: list[LeituraOut] | list[LeituraAgregadaOut]


class ErroOut(BaseModel):
    recebido_em: datetime
    topico: str | None
    motivo: str
    payload: str | None  # truncado em 500 caracteres
