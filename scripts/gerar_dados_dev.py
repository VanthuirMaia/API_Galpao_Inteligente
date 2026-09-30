"""Gera dados de exemplo para DESENVOLVIMENTO do painel. Nunca use em produção.

Uso: DATABASE_URL=postgresql://galpao:galpao_dev@localhost:5433/galpao python scripts/gerar_dados_dev.py
Recusa rodar se o banco não for localhost. Idempotente: pode rodar de novo sem duplicar.
"""
import math
import os
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.types.json import Jsonb

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "ingestor"))
sys.path.insert(0, str(RAIZ / "api"))
from itgu import itgu_de_leitura  # noqa: E402
from app.seguranca import hash_senha  # noqa: E402

DIAS = 7
RECIFE = ZoneInfo("America/Recife")
SENHA_LEITOR = "leitor-dev-12345"

# ATENÇÃO: valores INVENTADOS, só para ver as cores do painel funcionando.
# NÃO são valores técnicos. As faixas reais vêm do professor e são cadastradas pelo painel.
FAIXAS_EXEMPLO = [
    ("EXEMPLO - Semana 1", 0, 7, 70, 74, 79, 84),
    ("EXEMPLO - Semana 2", 8, 14, 69, 73, 79, 85),
    ("EXEMPLO - Semana 3", 15, 21, 68, 72, 80, 86),
]

# perfil de cada galpão: acréscimo de temperatura interna em relação à externa e ruído
PERFIS = {"esp01": {"extra": 1.5}, "esp02": {"extra": 2.8}}


def exigir_localhost(url: str) -> None:
    host = conninfo_to_dict(url).get("host", "")
    if host not in ("localhost", "127.0.0.1", "::1"):
        sys.exit(f"RECUSADO: DATABASE_URL aponta para '{host}'. Este script só roda em banco local de dev.")


def leitura_sintetica(device_id: str, ts: datetime) -> dict:
    """Uma leitura com ciclo diário (mais quente à tarde) e ruído leve, determinística por (device, ts)."""
    rng = random.Random(f"{device_id}-{int(ts.timestamp())}")
    h = ts.astimezone(RECIFE)
    hora_dec = h.hour + h.minute / 60
    t_ext = 27 + 6 * math.sin(2 * math.pi * (hora_dec - 9) / 24)  # pico às 15 h
    t_int = t_ext + PERFIS[device_id]["extra"] + rng.gauss(0, 0.25)
    t_globo = t_int + 0.9 + rng.gauss(0, 0.2)
    ur_int = min(95, max(35, 72 - (t_ext - 27) * 2.6 + rng.gauss(0, 1.2)))
    ur_ext = min(98, max(30, 68 - (t_ext - 27) * 2.8 + rng.gauss(0, 1.5)))
    tpo, itgu = itgu_de_leitura(t_int, ur_int, t_globo)
    return {
        "device_id": device_id, "ts": ts, "t_int": round(t_int, 2), "ur_int": round(ur_int, 1),
        "t_globo": round(t_globo, 2), "t_ext": round(t_ext + rng.gauss(0, 0.3), 2), "ur_ext": round(ur_ext, 1),
        "tpo": round(tpo, 2), "itgu": round(itgu, 2), "rssi": rng.randint(-75, -55),
    }


def gerar_leituras(conn, agora: datetime) -> int:
    fim = agora.replace(second=0, microsecond=0)
    ontem = (fim.astimezone(RECIFE) - timedelta(days=1)).date()
    # esp02: buraco de 2 h ontem, das 13:00 às 15:00 (hora de Recife)
    buraco_ini = datetime(ontem.year, ontem.month, ontem.day, 13, tzinfo=RECIFE)
    buraco_fim = buraco_ini + timedelta(hours=2)

    sql = (
        "INSERT INTO galpao.leituras (device_id, ts, ts_origem, recebido_em, t_int, ur_int, t_globo, "
        "t_ext, ur_ext, tpo, itgu, rssi, payload) "
        "VALUES (%(device_id)s, %(ts)s, 'esp', %(ts)s, %(t_int)s, %(ur_int)s, %(t_globo)s, %(t_ext)s, "
        "%(ur_ext)s, %(tpo)s, %(itgu)s, %(rssi)s, %(payload)s) ON CONFLICT (device_id, ts) DO NOTHING"
    )
    total = 0
    for device_id in PERFIS:
        linhas = []
        for i in range(DIAS * 24 * 60):
            ts = fim - timedelta(minutes=i)
            if device_id == "esp02" and buraco_ini <= ts < buraco_fim:
                continue
            linhas.append({**leitura_sintetica(device_id, ts), "payload": Jsonb({"dev": True})})
        with conn.cursor() as cur:
            cur.executemany(sql, linhas)
            total += cur.rowcount
    return total


def preparar_cadastros(conn, agora: datetime) -> None:
    for nome, ini, fim, cmin, mmin, mmax, cmax in FAIXAS_EXEMPLO:
        conn.execute(
            "INSERT INTO galpao.faixas_itgu (nome, idade_inicio_dias, idade_fim_dias, critico_min, conforto_min, "
            "conforto_max, critico_max) SELECT %s, %s, %s, %s, %s, %s, %s "
            "WHERE NOT EXISTS (SELECT 1 FROM galpao.faixas_itgu WHERE nome = %s)",
            (nome, ini, fim, cmin, mmin, mmax, cmax, nome),
        )
    hoje = agora.astimezone(RECIFE).date()
    conn.execute(
        "UPDATE galpao.dispositivos SET data_alojamento = %s WHERE id = 'esp02'", (hoje - timedelta(days=20),)
    )
    conn.execute(
        "INSERT INTO galpao.usuarios (email, nome, senha_hash, perfil) VALUES ('leitor@galpao.dev', 'Leitor de Teste', %s, 'leitor') "
        "ON CONFLICT (email) DO NOTHING",
        (hash_senha(SENHA_LEITOR),),
    )


def gerar_erros(conn, agora: datetime) -> None:
    ja_existe = conn.execute("SELECT count(*) FROM galpao.erros_ingestao WHERE payload LIKE '%dev-exemplo%'").fetchone()[0]
    if ja_existe:
        return
    exemplos = [
        (5, "galpao/esp01/leituras", "json_invalido", '{"device_id": "esp01", "dev-exemplo": true, "interno": {"t": 2'),
        (42, "galpao/esp02/leituras", "campo_ausente:globo.t", '{"device_id":"esp02","dev-exemplo":true,"interno":{"t":29.1,"ur":64}}'),
        (130, "galpao/esp01/leituras", "fora_da_faixa:interno.ur", '{"device_id":"esp01","dev-exemplo":true,"interno":{"t":30,"ur":140},"globo":{"t":31}}'),
        (600, "galpao/esp99/leituras", "device_desconhecido", '{"device_id":"esp99","dev-exemplo":true}'),
    ]
    for minutos, topico, motivo, payload in exemplos:
        conn.execute(
            "INSERT INTO galpao.erros_ingestao (recebido_em, topico, motivo, payload) VALUES (%s, %s, %s, %s)",
            (agora - timedelta(minutes=minutos), topico, motivo, payload),
        )


def main() -> None:
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL não definida")
    exigir_localhost(url)

    agora = datetime.now(timezone.utc)
    with psycopg.connect(url, autocommit=True) as conn:
        preparar_cadastros(conn, agora)
        novas = gerar_leituras(conn, agora)
        gerar_erros(conn, agora)
    print(f"leituras novas: {novas} | leitor de teste: leitor@galpao.dev / {SENHA_LEITOR}")


if __name__ == "__main__":
    main()
