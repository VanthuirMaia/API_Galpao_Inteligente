from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.classificacao import hoje_recife  # noqa: E402

SENHA_MIN = 10


class FaixaResumoOut(BaseModel):
    id: int
    nome: str
    critico_min: float
    conforto_min: float
    conforto_max: float
    critico_max: float


class SituacaoOut(BaseModel):
    idade_dias: int | None
    origem_faixa: Literal["manual", "idade"] | None
    faixa: FaixaResumoOut | None
    classificacao: Literal["conforto", "alerta", "critico", "sem_faixa"] | None  # null: sem leitura


class DispositivoOut(BaseModel):
    id: str
    ambiente: str
    descricao: str | None
    ativo: bool
    data_alojamento: date | None
    faixa_manual_id: int | None
    ultima_leitura_em: datetime | None
    online: bool
    situacao: SituacaoOut


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
    situacao: SituacaoOut


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
    data_alojamento: date | None
    faixa_manual_id: int | None
    criado_em: datetime


class DispositivoCriadoOut(DispositivoBaseOut):
    aviso: str


class DispositivoPatch(BaseModel):
    descricao: str | None = None  # null apaga a descrição
    ambiente: Literal["modelo", "real"] | None = None
    ativo: bool | None = None
    data_alojamento: date | None = None  # null limpa
    faixa_manual_id: int | None = None  # null volta a usar a faixa pela idade

    @field_validator("data_alojamento")
    @classmethod
    def _nao_futura(cls, v):
        if v is not None and v > hoje_recife():
            raise ValueError("data_alojamento não pode ser futura")
        return v

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


class TokenSenhaOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ---------- faixas de ITGU ----------

def erro_faixa(f: dict) -> str | None:
    """Mensagem de erro se idades ou limites da faixa estão fora de ordem; senão None."""
    if f["idade_fim_dias"] < f["idade_inicio_dias"]:
        return "idade_fim_dias deve ser >= idade_inicio_dias"
    if not f["critico_min"] < f["conforto_min"] < f["conforto_max"] < f["critico_max"]:
        return "limites devem obedecer critico_min < conforto_min < conforto_max < critico_max"
    return None


class FaixaIn(BaseModel):
    nome: str = Field(min_length=1)
    idade_inicio_dias: int = Field(ge=0)
    idade_fim_dias: int = Field(ge=0)
    critico_min: float
    conforto_min: float
    conforto_max: float
    critico_max: float

    @model_validator(mode="after")
    def _ordem(self):
        erro = erro_faixa(self.model_dump())
        if erro:
            raise ValueError(erro)
        return self


class FaixaPatch(BaseModel):
    nome: str | None = Field(None, min_length=1)
    idade_inicio_dias: int | None = Field(None, ge=0)
    idade_fim_dias: int | None = Field(None, ge=0)
    critico_min: float | None = None
    conforto_min: float | None = None
    conforto_max: float | None = None
    critico_max: float | None = None
    ativo: bool | None = None

    @model_validator(mode="after")
    def _validar(self):
        # a ordem dos limites é checada na rota, com os valores atuais dos campos não enviados
        return _exigir_campos(self, tuple(type(self).model_fields))


class FaixaOut(BaseModel):
    id: int
    nome: str
    idade_inicio_dias: int
    idade_fim_dias: int
    critico_min: float
    conforto_min: float
    conforto_max: float
    critico_max: float
    ativo: bool
    criado_em: datetime
