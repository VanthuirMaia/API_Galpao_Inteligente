import importlib

import pytest
from fastapi.testclient import TestClient

import app.main


@pytest.fixture
def app_com_prefixo(monkeypatch):
    """App recriado com ROOT_PATH=/api (lido na criação do app). Restaura ao final."""
    monkeypatch.setenv("ROOT_PATH", "/api")
    yield importlib.reload(app.main).app
    monkeypatch.undo()
    importlib.reload(app.main)


def test_openapi_declara_o_servidor_com_prefixo(app_com_prefixo):
    # sem `with`: não roda o lifespan, nem precisa de banco
    r = TestClient(app_com_prefixo).get("/openapi.json")
    assert r.status_code == 200
    assert r.json()["servers"] == [{"url": "/api"}]


@pytest.mark.parametrize("prefixo", ["/api", ""])
def test_token_url_relativo_no_swagger(monkeypatch, prefixo):
    """Sem barra inicial, o Swagger resolve /api/docs -> /api/auth/login e /docs -> /auth/login."""
    monkeypatch.setenv("ROOT_PATH", prefixo)
    try:
        esquemas = TestClient(importlib.reload(app.main).app).get("/openapi.json").json()["components"]["securitySchemes"]
        assert esquemas["OAuth2PasswordBearer"]["flows"]["password"]["tokenUrl"] == "auth/login"
    finally:
        monkeypatch.undo()
        importlib.reload(app.main)


def test_rotas_respondem_sem_o_prefixo(app_com_prefixo):
    # o Traefik remove /api antes de repassar: a API continua atendendo em /saude, /auth/...
    c = TestClient(app_com_prefixo)
    assert c.get("/saude").status_code == 200
    assert c.get("/auth/me").status_code == 401


def test_sem_root_path_nao_declara_servidor(monkeypatch):
    monkeypatch.delenv("ROOT_PATH", raising=False)
    sem_prefixo = importlib.reload(app.main).app
    assert "servers" not in TestClient(sem_prefixo).get("/openapi.json").json()


def test_database_url_api_tem_prioridade(monkeypatch):
    from app import config
    monkeypatch.setenv("DATABASE_URL", "postgresql://ingestor@h/db")
    monkeypatch.setenv("DATABASE_URL_API", "postgresql://api@h/db")
    assert config.database_url() == "postgresql://api@h/db"
    monkeypatch.delenv("DATABASE_URL_API")
    assert config.database_url() == "postgresql://ingestor@h/db"  # fallback
