from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, model_validator

SENHA_MIN = 10


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


# ---------- escrita (administração) ----------

class DispositivoIn(BaseModel):
    # o id também é usuário MQTT e parte do tópico: sem "/", "+", "#" nem maiúsculas
    id: str = Field(pattern=r"^[a-z0-9_-]{3,32}$")
    ambiente: Literal["modelo", "real"]
    descricao: str | None = None


class DispositivoBaseOut(BaseModel):
    id: str
    ambiente: str
    descricao: str | None
    ativo: bool
    criado_em: datetime


class DispositivoCriadoOut(DispositivoBaseOut):
    aviso: str


class DispositivoPatch(BaseModel):
    descricao: str | None = None  # null apaga a descrição
    ambiente: Literal["modelo", "real"] | None = None
    ativo: bool | None = None

    @model_validator(mode="after")
    def _validar(self):
        return _exigir_campos(self, ("ambiente", "ativo"))


class UsuarioCriarIn(BaseModel):
    email: EmailStr
    nome: str = Field(min_length=1)
    perfil: Literal["admin", "leitor"]
    senha: str = Field(min_length=SENHA_MIN)


class UsuarioPatch(BaseModel):
    nome: str | None = Field(None, min_length=1)
    perfil: Literal["admin", "leitor"] | None = None
    ativo: bool | None = None

    @model_validator(mode="after")
    def _validar(self):
        return _exigir_campos(self, ("nome", "perfil", "ativo"))


class SenhaIn(BaseModel):
    senha: str = Field(min_length=SENHA_MIN)


class SenhaAlterarIn(BaseModel):
    senha_atual: str
    senha_nova: str = Field(min_length=SENHA_MIN)

    @model_validator(mode="after")
    def _diferente(self):
        if self.senha_nova == self.senha_atual:
            raise ValueError("a senha nova deve ser diferente da atual")
        return self


class UsuarioAdminOut(BaseModel):
    id: int
    email: str
    nome: str
    perfil: str
    ativo: bool
    criado_em: datetime
    ultimo_login: datetime | None


def _exigir_campos(modelo, nao_nulos: tuple[str, ...]):
    """PATCH: corpo vazio é erro, e campos que não aceitam null não podem vir null."""
    enviados = modelo.model_fields_set
    if not enviados:
        raise ValueError("informe ao menos um campo")
    for campo in nao_nulos:
        if campo in enviados and getattr(modelo, campo) is None:
            raise ValueError(f"{campo} não pode ser nulo")
    return modelo
