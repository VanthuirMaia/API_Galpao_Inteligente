from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

FUSO = ZoneInfo("America/Recife")


def hoje_recife(agora: datetime | None = None) -> date:
    """Data atual no fuso de Recife (é a que define a idade do lote)."""
    agora = agora or datetime.now(timezone.utc)
    return agora.astimezone(FUSO).date()


def idade_em_dias(data_alojamento: date, hoje: date) -> int:
    """Dia do alojamento = idade 0."""
    return (hoje - data_alojamento).days


def escolher_faixa(dispositivo: dict, faixas_ativas: list[dict], hoje: date):
    """Devolve (faixa | None, origem "manual" | "idade" | None, idade_dias | None).

    Faixa manual tem prioridade; senão vale a faixa ativa que cobre a idade do lote.
    """
    alojamento = dispositivo.get("data_alojamento")
    idade = idade_em_dias(alojamento, hoje) if alojamento else None

    manual_id = dispositivo.get("faixa_manual_id")
    if manual_id is not None:
        for f in faixas_ativas:
            if f["id"] == manual_id:
                return f, "manual", idade

    if idade is not None:
        for f in faixas_ativas:
            if f["idade_inicio_dias"] <= idade <= f["idade_fim_dias"]:
                return f, "idade", idade

    return None, None, idade


def classificar(itgu: float, faixa: dict | None) -> str:
    """"conforto" | "alerta" | "critico" | "sem_faixa"."""
    if faixa is None:
        return "sem_faixa"
    if faixa["conforto_min"] <= itgu <= faixa["conforto_max"]:
        return "conforto"
    if itgu < faixa["critico_min"] or itgu > faixa["critico_max"]:
        return "critico"
    return "alerta"


def situacao(dispositivo: dict, itgu: float | None, faixas_ativas: list[dict], hoje: date) -> dict:
    """Bloco "situacao" de um dispositivo. classificacao é None se não há leitura."""
    faixa, origem, idade = escolher_faixa(dispositivo, faixas_ativas, hoje)
    return {
        "idade_dias": idade,
        "origem_faixa": origem,
        "faixa": faixa,
        "classificacao": None if itgu is None else classificar(itgu, faixa),
    }
