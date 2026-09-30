from datetime import datetime

import psycopg

from db import buscar_ativos, inserir_leitura, registrar_erro
from itgu import itgu_de_leitura
from validacao import validar

ERRO_CALCULO = "erro_calculo"


def novo_cache() -> dict:
    """Cache de dispositivos ativos."""
    return {"ids": set(), "carregado_em": None}


def ativos_em_cache(conn: psycopg.Connection, cache: dict, agora: datetime, ttl_s: int = 300) -> set[str]:
    """Devolve os ativos do cache; recarrega do banco se vazio ou vencido (mais de ttl_s)."""
    carregado_em = cache["carregado_em"]
    if carregado_em is None or (agora - carregado_em).total_seconds() > ttl_s:
        cache["ids"] = buscar_ativos(conn)
        cache["carregado_em"] = agora
    return cache["ids"]


def processar_mensagem(conn: psycopg.Connection, cache: dict, topico: str, dados: bytes, agora: datetime) -> str:
    """Valida, calcula e grava. Retorna "gravada", "duplicada" ou "rejeitada:<motivo>".

    Erros de banco sobem para quem chamou (a reconexão é do main).
    """
    ativos = ativos_em_cache(conn, cache, agora)
    leitura, motivo = validar(topico, dados, ativos, agora)
    if motivo is not None:
        registrar_erro(conn, topico, dados, motivo)
        return f"rejeitada:{motivo}"

    try:
        tpo, itgu = itgu_de_leitura(leitura["t_int"], leitura["ur_int"], leitura["t_globo"])
    except ValueError:
        registrar_erro(conn, topico, dados, ERRO_CALCULO)
        return f"rejeitada:{ERRO_CALCULO}"

    return "gravada" if inserir_leitura(conn, leitura, tpo, itgu) else "duplicada"
