import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

URL = os.environ.get("DATABASE_URL_TEST")
if not URL:
    pytest.skip("DATABASE_URL_TEST não definida", allow_module_level=True)

import psycopg
from fastapi.testclient import TestClient

from app.main import app
from app.seguranca import criar_token, hash_senha

DB = Path(__file__).parent.parent.parent / "db"
SENHA = "senha-de-teste-123"
HASH = hash_senha(SENHA)  # um hash só, reaproveitado


@pytest.fixture(scope="module")
def conn():
    with psycopg.connect(URL, autocommit=True) as c:
        for arq in ("001_init.sql", "002_permissoes.sql", "003_usuarios_api.sql", "004_faixas_itgu.sql"):
            c.execute((DB / arq).read_text(encoding="utf-8"))
        yield c


@pytest.fixture
def client(conn, monkeypatch):
    conn.execute("TRUNCATE galpao.usuarios RESTART IDENTITY")
    conn.execute(
        "INSERT INTO galpao.usuarios (email, nome, senha_hash, perfil, ativo) VALUES "
        "('admin@teste.com', 'Admin', %s, 'admin', true),"
        "('leitor@teste.com', 'Leitor', %s, 'leitor', true),"
        "('inativo@teste.com', 'Inativo', %s, 'leitor', false)",
        (HASH, HASH, HASH),
    )
    monkeypatch.setenv("DATABASE_URL", URL)
    with TestClient(app) as c:
        yield c


def login(client, email, senha=SENHA):
    return client.post("/auth/login", data={"username": email, "password": senha})


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_saude_sem_login(client):
    r = client.get("/saude")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "banco": True}


@pytest.mark.parametrize("email, perfil, nome", [
    ("admin@teste.com", "admin", "Admin"),
    ("leitor@teste.com", "leitor", "Leitor"),
])
def test_login_correto(client, email, perfil, nome):
    r = login(client, email)
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["access_token"] and corpo["token_type"] == "bearer"
    assert corpo["perfil"] == perfil and corpo["nome"] == nome


def test_login_falhas_tem_a_mesma_resposta(client):
    respostas = [
        login(client, "admin@teste.com", "senha-errada-123"),
        login(client, "naoexiste@teste.com"),
        login(client, "inativo@teste.com"),  # senha certa, mas inativo
    ]
    for r in respostas:
        assert r.status_code == 401
        assert r.json() == {"detail": "credenciais inválidas"}


def test_login_com_email_em_maiusculas(client):
    assert login(client, "ADMIN@Teste.COM").status_code == 200


def test_me_sem_token(client):
    assert client.get("/auth/me").status_code == 401


def test_me_com_token_valido(client):
    token = login(client, "leitor@teste.com").json()["access_token"]
    r = client.get("/auth/me", headers=auth(token))
    assert r.status_code == 200
    assert r.json() == {"id": 2, "email": "leitor@teste.com", "nome": "Leitor", "perfil": "leitor"}
    assert "senha_hash" not in r.json()


def test_me_com_token_expirado(client):
    token = criar_token(1, "admin", agora=datetime.now(timezone.utc) - timedelta(days=2))
    assert client.get("/auth/me", headers=auth(token)).status_code == 401


def test_me_com_token_de_usuario_inexistente(client):
    assert client.get("/auth/me", headers=auth(criar_token(999, "admin"))).status_code == 401


def test_desativado_depois_do_token(client, conn):
    token = login(client, "leitor@teste.com").json()["access_token"]
    assert client.get("/auth/me", headers=auth(token)).status_code == 200
    conn.execute("UPDATE galpao.usuarios SET ativo = false WHERE email = 'leitor@teste.com'")
    assert client.get("/auth/me", headers=auth(token)).status_code == 401


def test_perfil_vem_do_banco_nao_do_token(client, conn):
    # token diz admin, mas o usuário no banco é leitor: /auth/me mostra o perfil do banco
    token = criar_token(2, "admin")
    assert client.get("/auth/me", headers=auth(token)).json()["perfil"] == "leitor"


def test_ultimo_login_preenchido(client, conn):
    antes = conn.execute("SELECT ultimo_login FROM galpao.usuarios WHERE email = 'admin@teste.com'").fetchone()[0]
    assert antes is None
    login(client, "admin@teste.com")
    depois = conn.execute("SELECT ultimo_login FROM galpao.usuarios WHERE email = 'admin@teste.com'").fetchone()[0]
    assert depois is not None


def test_003_idempotente(conn):
    sql = (DB / "003_usuarios_api.sql").read_text(encoding="utf-8")
    conn.execute(sql)
    conn.execute(sql)
    existe = conn.execute("SELECT 1 FROM pg_roles WHERE rolname = 'galpao_leitura'").fetchone()
    assert existe is None
