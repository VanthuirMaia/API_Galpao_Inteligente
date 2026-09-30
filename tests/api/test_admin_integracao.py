import json
import os
from concurrent.futures import ThreadPoolExecutor
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
from processamento import novo_cache, processar_mensagem  # do ingestor

DB = Path(__file__).parent.parent.parent / "db"
SENHA = "senha-de-teste-123"
HASH = hash_senha(SENHA)


@pytest.fixture(scope="module")
def conn():
    with psycopg.connect(URL, autocommit=True) as c:
        for arq in ("001_init.sql", "002_permissoes.sql", "003_usuarios_api.sql", "004_faixas_itgu.sql"):
            c.execute((DB / arq).read_text(encoding="utf-8"))
        yield c


@pytest.fixture
def client(conn, monkeypatch):
    """Estado limpo por teste: usuários 1 (admin) e 2 (leitor); só esp01 e esp02 cadastrados."""
    conn.execute("TRUNCATE galpao.leituras, galpao.erros_ingestao")
    conn.execute("DELETE FROM galpao.dispositivos WHERE id NOT IN ('esp01', 'esp02')")
    conn.execute("UPDATE galpao.dispositivos SET ativo = true, ambiente = CASE id WHEN 'esp01' THEN 'modelo' ELSE 'real' END")
    conn.execute("TRUNCATE galpao.usuarios RESTART IDENTITY")
    conn.execute(
        "INSERT INTO galpao.usuarios (email, nome, senha_hash, perfil) VALUES "
        "('admin@teste.com', 'Admin', %s, 'admin'), ('leitor@teste.com', 'Leitor', %s, 'leitor')",
        (HASH, HASH),
    )
    monkeypatch.setenv("DATABASE_URL", URL)
    with TestClient(app) as c:
        yield c


def cab(usuario_id: int, perfil: str) -> dict:
    return {"Authorization": f"Bearer {criar_token(usuario_id, perfil)}"}


ADMIN = lambda: cab(1, "admin")  # noqa: E731
LEITOR = lambda: cab(2, "leitor")  # noqa: E731


def novo_usuario(client, email="novo@teste.com", perfil="leitor", senha="senha-nova-12345", **extra):
    return client.post(
        "/usuarios",
        json={"email": email, "nome": "Novo", "perfil": perfil, "senha": senha, **extra},
        headers=ADMIN(),
    )


def login(client, email, senha):
    return client.post("/auth/login", data={"username": email, "password": senha})


# ---------- permissões ----------

ESCRITAS = [
    ("post", "/dispositivos", {"id": "esp10", "ambiente": "real"}),
    ("patch", "/dispositivos/esp01", {"ativo": False}),
    ("get", "/usuarios", None),
    ("post", "/usuarios", {"email": "a@teste.com", "nome": "A", "perfil": "leitor", "senha": "senha-longa-123"}),
    ("patch", "/usuarios/2", {"nome": "X"}),
    ("post", "/usuarios/2/senha", {"senha": "senha-longa-123"}),
]


@pytest.mark.parametrize("metodo, caminho, corpo", ESCRITAS)
def test_leitor_recebe_403(client, metodo, caminho, corpo):
    r = getattr(client, metodo)(caminho, headers=LEITOR(), **({"json": corpo} if corpo else {}))
    assert r.status_code == 403


@pytest.mark.parametrize("metodo, caminho, corpo", ESCRITAS)
def test_sem_token_recebe_401(client, metodo, caminho, corpo):
    r = getattr(client, metodo)(caminho, **({"json": corpo} if corpo else {}))
    assert r.status_code == 401


def test_leitor_nao_alterou_nada(client, conn):
    client.patch("/dispositivos/esp01", json={"ativo": False}, headers=LEITOR())
    assert conn.execute("SELECT ativo FROM galpao.dispositivos WHERE id = 'esp01'").fetchone()[0] is True


# ---------- dispositivos ----------

def test_criar_dispositivo(client):
    r = client.post("/dispositivos", json={"id": "esp10", "ambiente": "real", "descricao": "novo"}, headers=ADMIN())
    assert r.status_code == 201
    corpo = r.json()
    assert (corpo["id"], corpo["ambiente"], corpo["descricao"], corpo["ativo"]) == ("esp10", "real", "novo", True)
    assert corpo["aviso"] == "cadastre o usuário MQTT na VPS: scripts/criar_usuario_mqtt.sh esp10 <senha>"
    ids = [d["id"] for d in client.get("/dispositivos", headers=LEITOR()).json()]
    assert "esp10" in ids


@pytest.mark.parametrize("id_", ["ESP01", "esp/01", "e", "esp+1", "esp#1", "es", "a" * 33, "esp 1", ""])
def test_id_invalido_422(client, id_):
    r = client.post("/dispositivos", json={"id": id_, "ambiente": "real"}, headers=ADMIN())
    assert r.status_code == 422


def test_ambiente_invalido_422(client):
    assert client.post("/dispositivos", json={"id": "esp10", "ambiente": "x"}, headers=ADMIN()).status_code == 422


def test_dispositivo_repetido_409(client):
    r = client.post("/dispositivos", json={"id": "esp01", "ambiente": "real"}, headers=ADMIN())
    assert r.status_code == 409


def test_patch_dispositivo(client):
    r = client.patch("/dispositivos/esp01", json={"ativo": False, "descricao": "desligado"}, headers=ADMIN())
    assert r.status_code == 200
    assert r.json()["ativo"] is False and r.json()["id"] == "esp01"
    lista = {d["id"]: d for d in client.get("/dispositivos", headers=LEITOR()).json()}
    assert lista["esp01"]["ativo"] is False and lista["esp01"]["descricao"] == "desligado"

    r = client.patch("/dispositivos/esp01", json={"ambiente": "real", "ativo": True}, headers=ADMIN())
    assert r.json()["ambiente"] == "real" and r.json()["ativo"] is True
    assert r.json()["descricao"] == "desligado"  # o que não veio não muda


def test_patch_descricao_null_apaga(client):
    r = client.patch("/dispositivos/esp01", json={"descricao": None}, headers=ADMIN())
    assert r.status_code == 200 and r.json()["descricao"] is None


def test_patch_dispositivo_inexistente_404(client):
    assert client.patch("/dispositivos/esp99", json={"ativo": False}, headers=ADMIN()).status_code == 404


@pytest.mark.parametrize("corpo", [{}, {"ativo": None}, {"ambiente": None}, {"ambiente": "x"}, {"ativo": "talvez"}])
def test_patch_dispositivo_422(client, corpo):
    assert client.patch("/dispositivos/esp01", json=corpo, headers=ADMIN()).status_code == 422


def test_patch_nao_muda_o_id(client, conn):
    client.patch("/dispositivos/esp01", json={"id": "outro", "ativo": False}, headers=ADMIN())
    assert conn.execute("SELECT count(*) FROM galpao.dispositivos WHERE id = 'outro'").fetchone()[0] == 0


def test_dispositivo_criado_no_painel_chega_ao_ingestor(client, conn):
    """Ponta a ponta: cadastro pela API -> ingestor aceita depois do TTL do cache."""
    agora = datetime.now(timezone.utc)
    cache = novo_cache()

    def msg(device, ts):
        corpo = {"device_id": device, "ts": int(ts.timestamp()), "interno": {"t": 30, "ur": 70}, "globo": {"t": 32}}
        return f"galpao/{device}/leituras", json.dumps(corpo).encode()

    # mensagem do esp01 carrega o cache (novo id ainda não existe)
    assert processar_mensagem(conn, cache, *msg("esp01", agora), agora) == "gravada"

    assert client.post("/dispositivos", json={"id": "esp10", "ambiente": "real"}, headers=ADMIN()).status_code == 201

    # cache ainda válido: o novo dispositivo não é conhecido
    t1 = agora + timedelta(seconds=10)
    assert processar_mensagem(conn, cache, *msg("esp10", t1), t1) == "rejeitada:device_desconhecido"

    # passado o TTL, o cache recarrega e a leitura é gravada
    t2 = agora + timedelta(seconds=301)
    assert processar_mensagem(conn, cache, *msg("esp10", t2), t2) == "gravada"
    assert conn.execute("SELECT count(*) FROM galpao.leituras WHERE device_id = 'esp10'").fetchone()[0] == 1


# ---------- usuários ----------

def test_criar_usuario_e_email_minusculo(client):
    r = novo_usuario(client, email="Maria.Silva@Teste.COM")
    assert r.status_code == 201
    corpo = r.json()
    assert corpo["email"] == "maria.silva@teste.com"
    assert corpo["perfil"] == "leitor" and corpo["ativo"] is True and corpo["ultimo_login"] is None
    assert "senha" not in corpo and "senha_hash" not in corpo
    assert login(client, "maria.silva@teste.com", "senha-nova-12345").status_code == 200


def test_email_repetido_409_mesmo_com_maiusculas(client):
    assert novo_usuario(client, email="admin@teste.com").status_code == 409
    assert novo_usuario(client, email="ADMIN@teste.com").status_code == 409


@pytest.mark.parametrize("extra", [
    {"senha": "curta"},
    {"senha": "123456789"},  # 9 caracteres
    {"email": "nao-e-email"},
    {"perfil": "root"},
    {"nome": ""},
])
def test_criar_usuario_422(client, extra):
    assert novo_usuario(client, **extra).status_code == 422


def test_listar_usuarios_sem_hash(client):
    r = client.get("/usuarios", headers=ADMIN())
    assert r.status_code == 200
    assert [u["email"] for u in r.json()] == ["admin@teste.com", "leitor@teste.com"]
    for u in r.json():
        assert set(u) == {"id", "email", "nome", "perfil", "ativo", "criado_em", "ultimo_login"}


def test_patch_usuario(client):
    r = client.patch("/usuarios/2", json={"nome": "Outro Nome", "perfil": "admin"}, headers=ADMIN())
    assert r.status_code == 200
    assert r.json()["nome"] == "Outro Nome" and r.json()["perfil"] == "admin"


def test_patch_usuario_inexistente_404(client):
    assert client.patch("/usuarios/999", json={"nome": "X"}, headers=ADMIN()).status_code == 404


@pytest.mark.parametrize("corpo", [{}, {"perfil": "root"}, {"ativo": None}, {"nome": ""}])
def test_patch_usuario_422(client, corpo):
    assert client.patch("/usuarios/2", json=corpo, headers=ADMIN()).status_code == 422


# ---------- proteção do último admin ----------

def test_unico_admin_nao_pode_ser_rebaixado_nem_desativado(client, conn):
    for corpo in ({"perfil": "leitor"}, {"ativo": False}, {"perfil": "leitor", "ativo": False}):
        r = client.patch("/usuarios/1", json=corpo, headers=ADMIN())  # inclusive o próprio admin
        assert r.status_code == 409
        assert r.json()["detail"] == "o sistema precisa de pelo menos um admin ativo"
    assert conn.execute("SELECT perfil, ativo FROM galpao.usuarios WHERE id = 1").fetchone() == ("admin", True)


def test_dois_admins_um_pode_sair_o_outro_nao(client):
    assert client.patch("/usuarios/2", json={"perfil": "admin"}, headers=ADMIN()).status_code == 200
    assert client.patch("/usuarios/1", json={"perfil": "leitor"}, headers=ADMIN()).status_code == 200
    # agora só o 2 é admin
    r = client.patch("/usuarios/2", json={"perfil": "leitor"}, headers=cab(2, "admin"))
    assert r.status_code == 409


def test_admin_inativo_nao_conta(client, conn):
    # 2 vira admin inativo: o admin 1 continua sendo o único ativo
    conn.execute("UPDATE galpao.usuarios SET perfil = 'admin', ativo = false WHERE id = 2")
    assert client.patch("/usuarios/1", json={"ativo": False}, headers=ADMIN()).status_code == 409
    # mexer no admin inativo é livre
    assert client.patch("/usuarios/2", json={"perfil": "leitor"}, headers=ADMIN()).status_code == 200


def test_rebaixar_leitor_ou_nome_nao_aciona_protecao(client):
    assert client.patch("/usuarios/2", json={"nome": "Novo nome"}, headers=ADMIN()).status_code == 200
    assert client.patch("/usuarios/2", json={"ativo": False}, headers=ADMIN()).status_code == 200


def test_dois_admins_se_rebaixando_ao_mesmo_tempo(client, conn):
    """Nunca pode sobrar zero admin: exatamente um dos dois pedidos passa.

    O perdedor leva 409 (corrida pega pela trava) ou 403 (o outro já o rebaixou antes
    da autenticação dele): os dois são recusas corretas.
    """
    for _ in range(5):
        conn.execute("UPDATE galpao.usuarios SET perfil = 'admin', ativo = true WHERE id IN (1, 2)")

        def rebaixar(quem: int, alvo: int) -> int:
            return client.patch(f"/usuarios/{alvo}", json={"perfil": "leitor"}, headers=cab(quem, "admin")).status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            codigos = sorted(f.result() for f in [pool.submit(rebaixar, 1, 2), pool.submit(rebaixar, 2, 1)])
        assert codigos[0] == 200 and codigos[1] in (403, 409)
        assert conn.execute("SELECT count(*) FROM galpao.usuarios WHERE perfil = 'admin' AND ativo").fetchone()[0] == 1


# ---------- efeitos de desativar e redefinir senha ----------

def test_desativar_leitor_derruba_o_token(client):
    token = login(client, "leitor@teste.com", SENHA).json()["access_token"]
    cabecalho = {"Authorization": f"Bearer {token}"}
    assert client.get("/auth/me", headers=cabecalho).status_code == 200
    assert client.patch("/usuarios/2", json={"ativo": False}, headers=ADMIN()).status_code == 200
    assert client.get("/auth/me", headers=cabecalho).status_code == 401
    assert login(client, "leitor@teste.com", SENHA).status_code == 401


def test_admin_redefine_senha(client):
    r = client.post("/usuarios/2/senha", json={"senha": "outra-senha-456"}, headers=ADMIN())
    assert r.status_code == 204
    assert login(client, "leitor@teste.com", SENHA).status_code == 401
    assert login(client, "leitor@teste.com", "outra-senha-456").status_code == 200


def test_redefinir_senha_invalida_ou_inexistente(client):
    assert client.post("/usuarios/2/senha", json={"senha": "curta"}, headers=ADMIN()).status_code == 422
    assert client.post("/usuarios/999/senha", json={"senha": "outra-senha-456"}, headers=ADMIN()).status_code == 404


# ---------- troca da própria senha ----------

def trocar(client, cabecalho, atual, nova):
    return client.post("/auth/senha", json={"senha_atual": atual, "senha_nova": nova}, headers=cabecalho)


def test_trocar_propria_senha(client):
    r = trocar(client, LEITOR(), SENHA, "senha-trocada-789")
    assert r.status_code == 200 and r.json()["token_type"] == "bearer" and r.json()["access_token"]
    assert login(client, "leitor@teste.com", SENHA).status_code == 401
    assert login(client, "leitor@teste.com", "senha-trocada-789").status_code == 200


def test_trocar_senha_atual_errada_400(client):
    r = trocar(client, LEITOR(), "errada-errada-1", "senha-trocada-789")
    assert r.status_code == 400
    assert login(client, "leitor@teste.com", SENHA).status_code == 200  # nada mudou


@pytest.mark.parametrize("atual, nova", [(SENHA, SENHA), (SENHA, "curta")])
def test_trocar_senha_nova_invalida_422(client, atual, nova):
    assert trocar(client, LEITOR(), atual, nova).status_code == 422


def test_trocar_senha_sem_token_401(client):
    r = client.post("/auth/senha", json={"senha_atual": SENHA, "senha_nova": "senha-trocada-789"})
    assert r.status_code == 401
