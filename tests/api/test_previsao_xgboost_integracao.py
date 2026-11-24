"""GET /previsao com um modelo XGBoost de verdade: treinado pelo ml/rodar.py nos dados sintéticos.

Guarda contra o bug em que a imagem da API (xgboost-cpu, sem scikit-learn) devolvia 500 para
qualquer modelo XGBoost, porque XGBRegressor() exige scikit-learn. Os outros testes de /previsao
usam um modelo linear escrito à mão e não passam por esse caminho.

Precisa de DATABASE_URL_TEST e das dependências do treino (scikit-learn, matplotlib).
"""
import json
import math
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

URL = os.environ.get("DATABASE_URL_TEST")
if not URL:
    pytest.skip("DATABASE_URL_TEST não definida", allow_module_level=True)
pytest.importorskip("sklearn", reason="treinar o modelo (ml/rodar.py) precisa de scikit-learn")
pytest.importorskip("matplotlib", reason="ml/rodar.py gera gráficos com matplotlib")

import psycopg
from fastapi.testclient import TestClient

from app.main import app
from app.seguranca import hash_senha

RAIZ = Path(__file__).parent.parent.parent
DB = RAIZ / "db"
ML = RAIZ / "ml"
SENHA = "senha-de-teste-123"
DISPOSITIVO = "esp_xgb"
BASE = datetime.now(timezone.utc).replace(second=0, microsecond=0)
MIN = timedelta(minutes=1)


def valores(i: int) -> dict:
    """Leitura i minutos atrás: valores plausíveis (parecidos com o sintético), com uma oscilação suave."""
    onda = math.sin(i / 20)
    t_globo, tpo = 29.0 + onda, 22.0 + 0.3 * onda
    return {"t_int": 28.0 + onda, "ur_int": 70.0 - 2 * onda, "t_globo": t_globo,
            "t_ext": 27.0 + 0.5 * onda, "ur_ext": 68.0, "tpo": tpo, "itgu": t_globo + 0.36 * tpo + 41.5}


@pytest.fixture(scope="module")
def modelo_xgb(tmp_path_factory):
    """Pasta com um modelo XGBoost gerado pelo rodar.py (o linear ganha no MAE, então --tipo força o XGBoost)."""
    pasta = tmp_path_factory.mktemp("xgb")
    csv = pasta / "galpao_SINTETICO_10dias.csv"
    modelo = pasta / "modelo"
    py = [sys.executable]
    subprocess.run([*py, str(ML / "gerar_sintetico.py"), "--saida", str(csv)], check=True, cwd=ML)
    subprocess.run([*py, str(ML / "rodar.py"), "--csv", str(csv), "--saidas", str(pasta / "saidas"),
                    "--salvar-modelo", "--modelo-dir", str(modelo), "--tipo", "xgboost"],
                   check=True, cwd=ML, env={**os.environ, "MPLBACKEND": "Agg"})
    meta = json.loads((modelo / "metadados.json").read_text(encoding="utf-8"))
    assert meta["tipo"] == "xgboost" and meta["origem"] == "sintetico"
    return modelo


@pytest.fixture(scope="module")
def conn():
    with psycopg.connect(URL, autocommit=True) as c:
        for arq in ("001_init.sql", "002_permissoes.sql", "003_usuarios_api.sql", "004_faixas_itgu.sql", "005_faixas_limites_opcionais.sql"):
            c.execute((DB / arq).read_text(encoding="utf-8"))
        c.execute("TRUNCATE galpao.leituras, galpao.erros_ingestao, galpao.usuarios RESTART IDENTITY")
        c.execute("DELETE FROM galpao.faixas_itgu")
        c.execute(
            "INSERT INTO galpao.dispositivos (id, ambiente, descricao) VALUES (%s, 'modelo', 'teste xgboost') "
            "ON CONFLICT (id) DO NOTHING", (DISPOSITIVO,))
        c.execute(
            "INSERT INTO galpao.usuarios (email, nome, senha_hash, perfil) VALUES ('leitor@teste.com', 'Leitor', %s, 'leitor')",
            (hash_senha(SENHA),))
        sql = (
            "INSERT INTO galpao.leituras (device_id, ts, ts_origem, recebido_em, t_int, ur_int, t_globo, "
            "t_ext, ur_ext, tpo, itgu, rssi, payload) "
            "VALUES (%(device_id)s, %(ts)s, 'esp', %(ts)s, %(t_int)s, %(ur_int)s, %(t_globo)s, "
            "%(t_ext)s, %(ur_ext)s, %(tpo)s, %(itgu)s, -60, '{}')"
        )
        # 3 h seguidas, 1 por minuto, com todos os sensores (o modelo usa t_ext e ur_ext)
        c.cursor().executemany(sql, [{"device_id": DISPOSITIVO, "ts": BASE - i * MIN, **valores(i)} for i in range(180)])
        yield c
        c.execute("DELETE FROM galpao.leituras WHERE device_id = %s", (DISPOSITIVO,))
        c.execute("DELETE FROM galpao.dispositivos WHERE id = %s", (DISPOSITIVO,))


@pytest.fixture
def client(conn, modelo_xgb, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", URL)
    monkeypatch.setenv("MODELO_DIR", str(modelo_xgb))
    with TestClient(app) as c:
        yield c


def test_previsao_com_modelo_xgboost(client):
    token = client.post("/auth/login", data={"username": "leitor@teste.com", "password": SENHA}).json()["access_token"]
    r = client.get(f"/previsao?device_id={DISPOSITIVO}", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["status"] == "ok", j
    assert (j["modelo"], j["origem"], j["horizonte_min"]) == ("xgboost", "sintetico", 30)
    assert j["itgu_atual"] == pytest.approx(valores(0)["itgu"], abs=1e-3)
    # ITGU plausível, perto do atual (a série de teste varia ~1 ponto)
    assert abs(j["itgu_previsto"] - j["itgu_atual"]) < 5
    assert j["mae_teste"] > 0 and j["treinado_em"]
    assert datetime.fromisoformat(j["previsto_para"]) - datetime.fromisoformat(j["referencia_ts"]) == timedelta(minutes=30)


def test_xgboost_nao_exige_scikit_learn(modelo_xgb):
    """Carrega e prevê num processo em que `import sklearn` falha, como na imagem da API.

    Precisa ser outro processo: o xgboost decide no import se o scikit-learn existe, e aqui ele já foi importado.
    """
    codigo = (
        "import sys; sys.modules['sklearn'] = None\n"
        "import pandas as pd\n"
        "from modelo_io import carregar_modelo, prever\n"
        f"m = carregar_modelo(r'{modelo_xgb}')\n"
        "assert m['meta']['tipo'] == 'xgboost'\n"
        "X = pd.DataFrame([[1.0] * len(m['meta']['features'])], columns=m['meta']['features'])\n"
        "print(len(prever(m, X)))\n"
    )
    r = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True,
                       env={**os.environ, "PYTHONPATH": str(ML)})
    assert r.returncode == 0, r.stderr[-800:]
    assert r.stdout.strip() == "1"
