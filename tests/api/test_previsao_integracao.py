"""GET /previsao com Postgres real (DATABASE_URL_TEST) e um modelo linear mínimo escrito à mão."""
import json
import os
from datetime import date, datetime, timedelta, timezone
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
BASE = datetime.now(timezone.utc).replace(second=0, microsecond=0)
MIN = timedelta(minutes=1)

# ITGU constante nas leituras de esp01: t_globo + 0,36 * tpo + 41,5
ITGU = 29.0 + 0.36 * 19.5 + 41.5


def escrever_modelo(pasta: Path, features: list[str], coef: list[float], intercepto: float, origem="sintetico"):
    """Modelo linear mínimo no formato de ml/modelo_io.py (sem padronização: média 0, escala 1)."""
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "modelo_teste.json").write_text(json.dumps({
        "media": [0.0] * len(features), "escala": [1.0] * len(features),
        "coef": coef, "intercepto": intercepto,
    }), encoding="utf-8")
    (pasta / "metadados.json").write_text(json.dumps({
        "tipo": "linear", "formato": 1, "arquivo_modelo": "modelo_teste.json", "features": features,
        "horizonte_min": 30, "origem": origem, "mae_teste": 0.4, "rmse_teste": 0.5,
        "treinado_em": "2026-12-01T12:00:00+00:00",
    }), encoding="utf-8")


@pytest.fixture(scope="module")
def conn():
    with psycopg.connect(URL, autocommit=True) as c:
        for arq in ("001_init.sql", "002_permissoes.sql", "003_usuarios_api.sql", "004_faixas_itgu.sql"):
            c.execute((DB / arq).read_text(encoding="utf-8"))
        c.execute("TRUNCATE galpao.leituras, galpao.erros_ingestao, galpao.usuarios RESTART IDENTITY")
        c.execute("UPDATE galpao.dispositivos SET ativo = true, faixa_manual_id = NULL")
        c.execute("DELETE FROM galpao.faixas_itgu")
        c.execute(
            "INSERT INTO galpao.faixas_itgu (nome, idade_inicio_dias, idade_fim_dias, critico_min, "
            "conforto_min, conforto_max, critico_max) VALUES ('faixa de teste', 0, 60, 60, 65, 75, 80)"
        )
        c.execute("UPDATE galpao.dispositivos SET data_alojamento = %s WHERE id = 'esp01'", (date.today() - timedelta(days=10),))
        c.execute(
            "INSERT INTO galpao.usuarios (email, nome, senha_hash, perfil) VALUES ('leitor@teste.com', 'Leitor', %s, 'leitor')",
            (hash_senha(SENHA),),
        )
        sql = (
            "INSERT INTO galpao.leituras (device_id, ts, ts_origem, recebido_em, t_int, ur_int, t_globo, "
            "t_ext, ur_ext, tpo, itgu, rssi, payload) "
            "VALUES (%(device_id)s, %(ts)s, 'esp', %(ts)s, 28, 60, 29, NULL, NULL, 19.5, %(itgu)s, -60, '{}')"
        )
        # esp01: 100 min seguidos, 1 por minuto, sem t_ext; esp02: só dados de 3 dias atrás
        recentes = [{"device_id": "esp01", "ts": BASE - i * MIN, "itgu": ITGU} for i in range(100)]
        antigos = [{"device_id": "esp02", "ts": BASE - timedelta(days=3) - i * MIN, "itgu": ITGU} for i in range(100)]
        c.cursor().executemany(sql, recentes + antigos)
        yield c


@pytest.fixture(scope="module")
def modelo_dir(tmp_path_factory):
    """previsto = 0,5 * itgu + 0,5 * itgu_lag60min + 1  (itgu constante: ITGU + 1)."""
    pasta = tmp_path_factory.mktemp("modelo")
    escrever_modelo(pasta, ["itgu", "itgu_lag60min"], [0.5, 0.5], 1.0)
    return pasta


@pytest.fixture
def client(conn, modelo_dir, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", URL)
    monkeypatch.setenv("MODELO_DIR", str(modelo_dir))
    with TestClient(app) as c:
        yield c


@pytest.fixture
def h(client):
    r = client.post("/auth/login", data={"username": "leitor@teste.com", "password": SENHA})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_sem_token_401(client):
    assert client.get("/previsao?device_id=esp01").status_code == 401


def test_dispositivo_inexistente_404(client, h):
    assert client.get("/previsao?device_id=nao_existe", headers=h).status_code == 404


def test_previsao_ok(client, h):
    r = client.get("/previsao?device_id=esp01", headers=h)
    assert r.status_code == 200
    j = r.json()
    assert j["status"] == "ok" and j["motivo"] is None
    assert j["itgu_atual"] == pytest.approx(ITGU, abs=1e-3)
    assert j["itgu_previsto"] == pytest.approx(ITGU + 1, abs=0.01)
    assert j["horizonte_min"] == 30
    assert j["classificacao"] == "alerta"  # 78,5 está acima do conforto (75) e abaixo do crítico (80)
    assert (j["modelo"], j["origem"], j["mae_teste"]) == ("linear", "sintetico", 0.4)
    assert datetime.fromisoformat(j["previsto_para"]) - datetime.fromisoformat(j["referencia_ts"]) == timedelta(minutes=30)
    assert j["gerado_em"] and j["treinado_em"]


def test_sem_faixa(client, h, conn):
    conn.execute("UPDATE galpao.dispositivos SET data_alojamento = NULL WHERE id = 'esp01'")
    try:
        assert client.get("/previsao?device_id=esp01", headers=h).json()["classificacao"] == "sem_faixa"
    finally:
        conn.execute("UPDATE galpao.dispositivos SET data_alojamento = %s WHERE id = 'esp01'", (date.today() - timedelta(days=10),))


def test_dados_antigos_sao_insuficientes(client, h):
    j = client.get("/previsao?device_id=esp02", headers=h).json()
    assert j["status"] == "dados_insuficientes"
    assert "sem leituras" in j["motivo"]
    assert j["itgu_previsto"] is None


def test_sensor_ausente_e_insuficiente(client, h, tmp_path, monkeypatch):
    escrever_modelo(tmp_path, ["itgu", "t_ext"], [0.5, 0.5], 0.0)  # esp01 não tem t_ext
    monkeypatch.setenv("MODELO_DIR", str(tmp_path))
    j = client.get("/previsao?device_id=esp01", headers=h).json()
    assert j["status"] == "dados_insuficientes" and "t_ext" in j["motivo"]


def test_sem_modelo_instalado(client, h, tmp_path, monkeypatch):
    monkeypatch.setenv("MODELO_DIR", str(tmp_path / "vazio"))
    r = client.get("/previsao?device_id=esp01", headers=h)
    assert r.status_code == 200 and r.json()["status"] == "modelo_indisponivel"


def test_troca_do_modelo_sem_reiniciar(client, h, tmp_path, monkeypatch):
    escrever_modelo(tmp_path, ["itgu"], [1.0], 2.0, origem="real")
    monkeypatch.setenv("MODELO_DIR", str(tmp_path))
    j = client.get("/previsao?device_id=esp01", headers=h).json()
    assert j["origem"] == "real" and j["itgu_previsto"] == pytest.approx(ITGU + 2, abs=0.01)
    # troca os arquivos na mesma pasta: a próxima chamada já usa o modelo novo
    escrever_modelo(tmp_path, ["itgu"], [1.0], 3.0, origem="real")
    os.utime(tmp_path / "metadados.json", None)
    j = client.get("/previsao?device_id=esp01", headers=h).json()
    assert j["itgu_previsto"] == pytest.approx(ITGU + 3, abs=0.01)
