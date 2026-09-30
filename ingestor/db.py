import logging
import time

import psycopg
from psycopg.types.json import Jsonb

log = logging.getLogger(__name__)

BACKOFF_MAX_S = 30
PAYLOAD_ERRO_MAX = 4000


def conectar(url: str) -> psycopg.Connection:
    """Conecta ao Postgres com autocommit. Tenta para sempre, com backoff de 1s até 30s."""
    espera = 1
    while True:
        try:
            return psycopg.connect(url, autocommit=True)
        except psycopg.OperationalError as e:
            log.warning("falha ao conectar no banco (%s); nova tentativa em %ss", e, espera)
            time.sleep(espera)
            espera = min(espera * 2, BACKOFF_MAX_S)


def buscar_ativos(conn: psycopg.Connection) -> set[str]:
    """Ids dos dispositivos ativos."""
    rows = conn.execute("SELECT id FROM galpao.dispositivos WHERE ativo").fetchall()
    return {r[0] for r in rows}


def inserir_leitura(conn: psycopg.Connection, leitura: dict, tpo: float, itgu: float) -> bool:
    """Grava a leitura. True se inseriu, False se era duplicata (device_id, ts)."""
    row = conn.execute(
        """
        INSERT INTO galpao.leituras
            (device_id, ts, ts_origem, t_int, ur_int, t_globo, t_ext, ur_ext,
             tpo, itgu, rssi, payload)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (device_id, ts) DO NOTHING
        RETURNING id
        """,
        (
            leitura["device_id"],
            leitura["ts"],
            leitura["ts_origem"],
            leitura["t_int"],
            leitura["ur_int"],
            leitura["t_globo"],
            leitura["t_ext"],
            leitura["ur_ext"],
            round(tpo, 2),
            round(itgu, 2),
            leitura["rssi"],
            Jsonb(leitura["payload"]),
        ),
    ).fetchone()
    return row is not None


def registrar_erro(conn: psycopg.Connection, topico: str, dados: bytes, motivo: str) -> None:
    """Guarda a mensagem rejeitada (payload truncado em 4000 caracteres)."""
    payload = dados.decode("utf-8", errors="replace")[:PAYLOAD_ERRO_MAX]
    conn.execute(
        "INSERT INTO galpao.erros_ingestao (topico, payload, motivo) VALUES (%s, %s, %s)",
        (topico, payload, motivo),
    )
