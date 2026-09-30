import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

URL = os.environ.get("DATABASE_URL_TEST")
if not URL:
    pytest.skip("DATABASE_URL_TEST não definida", allow_module_level=True)

import psycopg

from processamento import novo_cache, processar_mensagem

SQL_INIT = Path(__file__).parent.parent / "db" / "001_init.sql"
AGORA = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
TS = int((AGORA - timedelta(seconds=5)).timestamp())


@pytest.fixture(scope="module")
def conn():
    with psycopg.connect(URL, autocommit=True) as c:
        c.execute(SQL_INIT.read_text(encoding="utf-8"))
        yield c


@pytest.fixture
def cache(conn):
    conn.execute("TRUNCATE galpao.leituras, galpao.erros_ingestao")
    conn.execute("UPDATE galpao.dispositivos SET ativo = true")
    return novo_cache()


def payload(device="esp01", t_int=30, ur_int=70, t_globo=32):
    return {
        "device_id": device,
        "ts": TS,
        "interno": {"t": t_int, "ur": ur_int},
        "globo": {"t": t_globo},
        "rssi": -60,
    }


def enviar(conn, cache, p, agora=AGORA):
    topico = f"galpao/{p['device_id']}/leituras"
    return processar_mensagem(conn, cache, topico, json.dumps(p).encode(), agora)


def test_leitura_valida(conn, cache):
    p = payload()
    assert enviar(conn, cache, p) == "gravada"
    row = conn.execute(
        "SELECT device_id, tpo, itgu, ts_origem, payload, ts FROM galpao.leituras"
    ).fetchall()
    assert len(row) == 1
    device_id, tpo, itgu, ts_origem, pl, ts = row[0]
    assert device_id == "esp01"
    assert tpo == pytest.approx(23.93, abs=0.01)
    assert itgu == pytest.approx(82.11, abs=0.01)
    assert ts_origem == "esp"
    assert pl == p
    assert ts == datetime.fromtimestamp(TS, tz=timezone.utc)


def test_duplicada(conn, cache):
    p = payload()
    assert enviar(conn, cache, p) == "gravada"
    assert enviar(conn, cache, p) == "duplicada"
    assert conn.execute("SELECT count(*) FROM galpao.leituras").fetchone()[0] == 1


def test_device_desconhecido(conn, cache):
    p = payload(device="esp99")
    assert enviar(conn, cache, p) == "rejeitada:device_desconhecido"
    assert conn.execute("SELECT count(*) FROM galpao.leituras").fetchone()[0] == 0
    erros = conn.execute("SELECT topico, motivo FROM galpao.erros_ingestao").fetchall()
    assert erros == [("galpao/esp99/leituras", "device_desconhecido")]


def test_bytes_invalidos(conn, cache):
    r = processar_mensagem(conn, cache, "galpao/esp01/leituras", b"\xff\xfe", AGORA)
    assert r == "rejeitada:json_invalido"
    motivo, pl = conn.execute("SELECT motivo, payload FROM galpao.erros_ingestao").fetchone()
    assert motivo == "json_invalido"
    assert pl == "��"  # bytes inválidos viram U+FFFD


def test_cache_ttl(conn, cache):
    # primeira mensagem carrega o cache com esp01 e esp02 ativos
    assert enviar(conn, cache, payload("esp01")) == "gravada"
    conn.execute("UPDATE galpao.dispositivos SET ativo = false WHERE id = 'esp02'")
    # cache recém-carregado: esp02 ainda passa
    assert enviar(conn, cache, payload("esp02")) == "gravada"
    # passou o ttl: recarrega do banco e esp02 some
    p2 = payload("esp02")
    p2["ts"] = TS + 1
    assert enviar(conn, cache, p2, AGORA + timedelta(seconds=301)) == "rejeitada:device_desconhecido"


def test_dois_dispositivos(conn, cache):
    assert enviar(conn, cache, payload("esp01")) == "gravada"
    assert enviar(conn, cache, payload("esp02")) == "gravada"
    devices = conn.execute("SELECT device_id FROM galpao.leituras ORDER BY device_id").fetchall()
    assert devices == [("esp01",), ("esp02",)]
