import csv
import io
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

URL = os.environ.get("DATABASE_URL_TEST")
if not URL:
    pytest.skip("DATABASE_URL_TEST não definida", allow_module_level=True)

import psycopg
from fastapi.testclient import TestClient

from app.main import app
from app.seguranca import hash_senha

DB = Path(__file__).parent.parent.parent / "db"
SENHA = "senha-de-teste-123"

# "agora" do teste, no minuto cheio
BASE = datetime.now(timezone.utc).replace(second=0, microsecond=0)
MIN = timedelta(minutes=1)


def gerar_dados() -> list[dict]:
    """esp01: 3 h de dados, 1 por minuto (i = minutos atrás). Valores determinísticos."""
    dados = []
    for i in range(180):
        t_int = 25 + (i % 10) * 0.5
        t_globo = t_int + 1
        tpo = t_int - 6
        dados.append({
            "device_id": "esp01", "ts": BASE - i * MIN,
            "t_int": t_int, "ur_int": 60 + (i % 7), "t_globo": t_globo,
            "t_ext": 28.0 if i % 2 == 0 else None, "ur_ext": 50.0 if i % 2 == 0 else None,
            "tpo": tpo, "itgu": t_globo + 0.36 * tpo + 41.5, "rssi": -60,
        })
    return dados


DADOS = gerar_dados()  # índice = minutos atrás


@pytest.fixture(scope="module")
def conn():
    with psycopg.connect(URL, autocommit=True) as c:
        for arq in ("001_init.sql", "002_permissoes.sql", "003_usuarios_api.sql", "004_faixas_itgu.sql"):
            c.execute((DB / arq).read_text(encoding="utf-8"))
        c.execute("TRUNCATE galpao.leituras, galpao.erros_ingestao, galpao.usuarios RESTART IDENTITY")
        c.execute("UPDATE galpao.dispositivos SET ativo = true")
        c.execute(
            "INSERT INTO galpao.dispositivos (id, ambiente, descricao, ativo) "
            "VALUES ('esp03', 'real', 'sem leituras', false) ON CONFLICT DO NOTHING"
        )
        c.execute("UPDATE galpao.dispositivos SET ativo = false WHERE id = 'esp03'")
        c.execute(
            "INSERT INTO galpao.usuarios (email, nome, senha_hash, perfil) VALUES ('leitor@teste.com', 'Leitor', %s, 'leitor')",
            (hash_senha(SENHA),),
        )

        sql = (
            "INSERT INTO galpao.leituras (device_id, ts, ts_origem, recebido_em, t_int, ur_int, t_globo, "
            "t_ext, ur_ext, tpo, itgu, rssi, payload) "
            "VALUES (%(device_id)s, %(ts)s, 'esp', %(ts)s, %(t_int)s, %(ur_int)s, %(t_globo)s, "
            "%(t_ext)s, %(ur_ext)s, %(tpo)s, %(itgu)s, %(rssi)s, '{}')"
        )
        c.cursor().executemany(sql, DADOS)
        # esp02: só dados antigos (3 dias atrás)
        antigos = [{**DADOS[i], "device_id": "esp02", "ts": BASE - timedelta(days=3) - i * MIN} for i in range(5)]
        c.cursor().executemany(sql, antigos)

        erros = [
            (BASE - 3 * MIN, "galpao/esp01/leituras", "json_invalido", "a"),
            (BASE - 2 * MIN, "galpao/esp02/leituras", "device_divergente", "b"),
            (BASE - 1 * MIN, "galpao/esp01/leituras", "campo_ausente:globo.t", "x" * 700),
        ]
        c.cursor().executemany(
            "INSERT INTO galpao.erros_ingestao (recebido_em, topico, motivo, payload) VALUES (%s, %s, %s, %s)", erros
        )
        yield c


@pytest.fixture(scope="module")
def client(conn):
    mp = pytest.MonkeyPatch()
    mp.setenv("DATABASE_URL", URL)
    with TestClient(app) as c:
        yield c
    mp.undo()


@pytest.fixture(scope="module")
def h(client):
    """Cabeçalho de autenticação de um leitor."""
    r = client.post("/auth/login", data={"username": "leitor@teste.com", "password": SENHA})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def iso(d: datetime) -> str:
    return d.isoformat()


def dt(texto: str) -> datetime:
    return datetime.fromisoformat(texto)


# ---------- autenticação ----------

@pytest.mark.parametrize("caminho", [
    "/dispositivos", "/dispositivos/esp01/ultima", "/leituras?device_id=esp01",
    "/leituras/csv?device_id=esp01", "/erros",
])
def test_sem_token_401(client, caminho):
    assert client.get(caminho).status_code == 401


# ---------- /dispositivos ----------

def test_dispositivos(client, h):
    r = client.get("/dispositivos", headers=h)
    assert r.status_code == 200
    por_id = {d["id"]: d for d in r.json()}
    assert set(por_id) == {"esp01", "esp02", "esp03"}  # ativos e inativos

    assert por_id["esp01"]["online"] is True
    assert dt(por_id["esp01"]["ultima_leitura_em"]) == BASE
    assert por_id["esp01"]["ambiente"] == "modelo"

    assert por_id["esp02"]["online"] is False  # última leitura de 3 dias atrás
    assert dt(por_id["esp02"]["ultima_leitura_em"]) == BASE - timedelta(days=3)

    assert por_id["esp03"]["online"] is False
    assert por_id["esp03"]["ultima_leitura_em"] is None
    assert por_id["esp03"]["ativo"] is False


def test_datas_em_utc(client, h):
    r = client.get("/dispositivos", headers=h)
    ts = next(d for d in r.json() if d["id"] == "esp01")["ultima_leitura_em"]
    assert re.search(r"(Z|\+00:00)$", ts)


# ---------- /dispositivos/{id}/ultima ----------

def test_ultima(client, h):
    r = client.get("/dispositivos/esp01/ultima", headers=h)
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["device_id"] == "esp01"
    leitura = corpo["leitura"]
    esperado = DADOS[0]
    assert dt(leitura["ts"]) == BASE and leitura["ts_origem"] == "esp"
    assert leitura["t_int"] == esperado["t_int"] and leitura["ur_int"] == esperado["ur_int"]
    assert leitura["t_globo"] == esperado["t_globo"] and leitura["t_ext"] == 28.0
    assert leitura["itgu"] == pytest.approx(esperado["itgu"], abs=0.001)
    assert leitura["rssi"] == -60
    assert "payload" not in leitura


def test_ultima_inexistente_404(client, h):
    assert client.get("/dispositivos/esp99/ultima", headers=h).status_code == 404


def test_ultima_sem_leituras(client, h):
    r = client.get("/dispositivos/esp03/ultima", headers=h)
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["device_id"] == "esp03" and corpo["leitura"] is None
    assert corpo["situacao"]["classificacao"] is None  # sem leitura, sem classificação


# ---------- /leituras ----------

def test_leituras_padrao_24h(client, h):
    r = client.get("/leituras", params={"device_id": "esp01"}, headers=h)
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["agregacao"] == "bruto" and corpo["total"] == 180 == len(corpo["itens"])
    assert dt(corpo["fim"]) - dt(corpo["inicio"]) == timedelta(hours=24)


def test_leituras_intervalo_e_ordem(client, h):
    params = {"device_id": "esp01", "inicio": iso(BASE - 10 * MIN), "fim": iso(BASE - 5 * MIN)}
    itens = client.get("/leituras", params=params, headers=h).json()["itens"]
    assert len(itens) == 6  # extremos inclusos
    tss = [dt(i["ts"]) for i in itens]
    assert tss == sorted(tss) and tss[0] == BASE - 10 * MIN and tss[-1] == BASE - 5 * MIN


def test_leituras_limite_pega_as_mais_recentes(client, h):
    itens = client.get("/leituras", params={"device_id": "esp01", "limite": 10}, headers=h).json()["itens"]
    assert len(itens) == 10
    tss = [dt(i["ts"]) for i in itens]
    assert tss == sorted(tss) and tss[-1] == BASE and tss[0] == BASE - 9 * MIN


@pytest.mark.parametrize("params", [
    {"inicio": "2026-01-02T00:00:00Z", "fim": "2026-01-01T00:00:00Z"},  # fim < inicio
    {"inicio": "2026-01-01T00:00:00Z", "fim": "2026-01-01T00:00:00Z"},  # fim == inicio
    {"inicio": "2026-01-01T00:00:00Z", "fim": "2026-02-02T00:00:01Z"},  # > 31 dias
    {"inicio": "2026-01-01T00:00:00", "fim": "2026-01-02T00:00:00Z"},   # sem fuso
    {"inicio": "2026-01-01T00:00:00Z", "fim": "2026-01-02T00:00:00"},   # sem fuso
    {"agregacao": "2h"},
    {"limite": 20001},
    {"limite": 0},
])
def test_leituras_422(client, h, params):
    r = client.get("/leituras", params={"device_id": "esp01", **params}, headers=h)
    assert r.status_code == 422


def test_leituras_31_dias_exatos_aceitos(client, h):
    params = {"device_id": "esp01", "inicio": "2026-01-01T00:00:00Z", "fim": "2026-02-01T00:00:00Z"}
    assert client.get("/leituras", params=params, headers=h).status_code == 200


def test_leituras_fuso_local_convertido(client, h):
    # mesmo instante em UTC-3: deve devolver o mesmo resultado
    local = timezone(timedelta(hours=-3))
    params = {"device_id": "esp01", "inicio": iso((BASE - 10 * MIN).astimezone(local)), "fim": iso(BASE.astimezone(local))}
    corpo = client.get("/leituras", params=params, headers=h).json()
    assert corpo["total"] == 11 and dt(corpo["fim"]) == BASE


def test_leituras_device_inexistente_404(client, h):
    assert client.get("/leituras", params={"device_id": "esp99"}, headers=h).status_code == 404


def test_leituras_device_obrigatorio(client, h):
    assert client.get("/leituras", headers=h).status_code == 422


# ---------- agregação ----------

def esperado_agregado(seg: int, inicio: datetime, fim: datetime) -> dict:
    grupos = {}
    for d in DADOS:
        if inicio <= d["ts"] <= fim:
            grupos.setdefault(int(d["ts"].timestamp() // seg * seg), []).append(d)
    return grupos


def media(linhas, campo):
    v = [x[campo] for x in linhas if x[campo] is not None]
    return sum(v) / len(v) if v else None


@pytest.mark.parametrize("agregacao, seg", [("5min", 300), ("15min", 900), ("1h", 3600)])
def test_agregacao(client, h, agregacao, seg):
    inicio, fim = BASE - timedelta(hours=3), BASE
    params = {"device_id": "esp01", "inicio": iso(inicio), "fim": iso(fim), "agregacao": agregacao}
    corpo = client.get("/leituras", params=params, headers=h).json()
    esperado = esperado_agregado(seg, inicio, fim)

    assert corpo["agregacao"] == agregacao and corpo["total"] == len(esperado)
    janelas = [dt(i["janela"]) for i in corpo["itens"]]
    assert janelas == sorted(janelas)
    assert [int(j.timestamp()) for j in janelas] == sorted(esperado)

    for item in corpo["itens"]:
        linhas = esperado[int(dt(item["janela"]).timestamp())]
        assert item["n"] == len(linhas)
        for campo in ("t_int", "ur_int", "t_globo", "t_ext", "ur_ext", "tpo", "itgu"):
            m = media(linhas, campo)
            if m is None:
                assert item[campo] is None
            else:
                assert item[campo] == pytest.approx(m, abs=0.011)  # arredondado em 2 casas
        assert item["itgu_min"] == pytest.approx(min(x["itgu"] for x in linhas), abs=0.011)
        assert item["itgu_max"] == pytest.approx(max(x["itgu"] for x in linhas), abs=0.011)


def test_agregacao_soma_das_leituras(client, h):
    params = {"device_id": "esp01", "inicio": iso(BASE - timedelta(hours=3)), "fim": iso(BASE), "agregacao": "1h"}
    itens = client.get("/leituras", params=params, headers=h).json()["itens"]
    assert sum(i["n"] for i in itens) == 180


# ---------- CSV ----------

def test_csv(client, h):
    inicio = BASE - timedelta(hours=2)
    params = {"device_id": "esp01", "inicio": iso(inicio), "fim": iso(BASE)}
    r = client.get("/leituras/csv", params=params, headers=h)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    nome = f"galpao_esp01_{inicio:%Y%m%d}_{BASE:%Y%m%d}.csv"
    assert f'filename="{nome}"' in r.headers["content-disposition"]

    assert r.text.splitlines()[0] == "ts,ts_origem,recebido_em,t_int,ur_int,t_globo,t_ext,ur_ext,tpo,itgu,rssi"
    linhas = list(csv.DictReader(io.StringIO(r.text)))
    assert len(linhas) == 121  # i = 0..120, extremos inclusos
    assert dt(linhas[0]["ts"]) == inicio and dt(linhas[-1]["ts"]) == BASE  # ordem crescente
    assert linhas[-1]["t_ext"] == "28.0"
    assert linhas[-2]["t_ext"] == ""  # minuto ímpar: sem sensor externo
    assert float(linhas[-1]["t_int"]) == DADOS[0]["t_int"]


def test_csv_agregado(client, h):
    params = {"device_id": "esp01", "inicio": iso(BASE - timedelta(hours=3)), "fim": iso(BASE), "agregacao": "1h"}
    r = client.get("/leituras/csv", params=params, headers=h)
    assert r.text.splitlines()[0] == "janela,n,t_int,ur_int,t_globo,t_ext,ur_ext,tpo,itgu,itgu_min,itgu_max"
    linhas = list(csv.DictReader(io.StringIO(r.text)))
    assert sum(int(x["n"]) for x in linhas) == 180


def test_csv_sem_limite_de_linhas(client, h, conn):
    # mais linhas que o lote de streaming (1000) e que o limite do JSON
    antigos = [
        {**DADOS[0], "device_id": "esp02", "ts": BASE - timedelta(days=10) - i * MIN}
        for i in range(2500)
    ]
    conn.cursor().executemany(
        "INSERT INTO galpao.leituras (device_id, ts, ts_origem, t_int, ur_int, t_globo, tpo, itgu, payload) "
        "VALUES (%(device_id)s, %(ts)s, 'esp', %(t_int)s, %(ur_int)s, %(t_globo)s, %(tpo)s, %(itgu)s, '{}')",
        antigos,
    )
    params = {"device_id": "esp02", "inicio": iso(BASE - timedelta(days=20)), "fim": iso(BASE - timedelta(days=5))}
    r = client.get("/leituras/csv", params=params, headers=h)
    assert len(list(csv.DictReader(io.StringIO(r.text)))) == 2500


@pytest.mark.parametrize("params, codigo", [
    ({"device_id": "esp99"}, 404),
    ({"device_id": "esp01", "inicio": "2026-01-01T00:00:00Z", "fim": "2026-03-01T00:00:00Z"}, 422),
    ({"device_id": "esp01", "inicio": "2026-01-01T00:00:00"}, 422),
])
def test_csv_mesmas_validacoes(client, h, params, codigo):
    assert client.get("/leituras/csv", params=params, headers=h).status_code == codigo


# ---------- /erros ----------

def test_erros_ordem(client, h):
    r = client.get("/erros", headers=h)
    assert r.status_code == 200
    assert [e["motivo"] for e in r.json()] == ["campo_ausente:globo.t", "device_divergente", "json_invalido"]
    assert dt(r.json()[0]["recebido_em"]) == BASE - MIN


def test_erros_filtro_por_device(client, h):
    itens = client.get("/erros", params={"device_id": "esp01"}, headers=h).json()
    assert [e["motivo"] for e in itens] == ["campo_ausente:globo.t", "json_invalido"]
    assert all(e["topico"] == "galpao/esp01/leituras" for e in itens)
    assert client.get("/erros", params={"device_id": "esp77"}, headers=h).json() == []


def test_erros_payload_truncado(client, h):
    itens = client.get("/erros", params={"device_id": "esp01"}, headers=h).json()
    assert len(itens[0]["payload"]) == 500 and itens[1]["payload"] == "a"


def test_erros_limite(client, h):
    assert len(client.get("/erros", params={"limite": 1}, headers=h).json()) == 1
    assert client.get("/erros", params={"limite": 501}, headers=h).status_code == 422
    assert client.get("/erros", params={"limite": 0}, headers=h).status_code == 422
