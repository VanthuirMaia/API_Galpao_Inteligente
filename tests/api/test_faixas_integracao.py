import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

URL = os.environ.get("DATABASE_URL_TEST")
if not URL:
    pytest.skip("DATABASE_URL_TEST não definida", allow_module_level=True)

import psycopg
from fastapi.testclient import TestClient

from app.classificacao import hoje_recife
from app.main import app
from app.seguranca import criar_token, hash_senha

DB = Path(__file__).parent.parent.parent / "db"
SENHA = "senha-de-teste-123"
HASH = hash_senha(SENHA)
AGORA = lambda: datetime.now(timezone.utc)  # noqa: E731


@pytest.fixture(scope="module")
def conn():
    with psycopg.connect(URL, autocommit=True) as c:
        for arq in ("001_init.sql", "002_permissoes.sql", "003_usuarios_api.sql", "004_faixas_itgu.sql"):
            c.execute((DB / arq).read_text(encoding="utf-8"))
        yield c


@pytest.fixture
def client(conn, monkeypatch):
    """Estado limpo: sem faixas, sem leituras, usuários 1 (admin) e 2 (leitor), só esp01 e esp02."""
    conn.execute("TRUNCATE galpao.leituras, galpao.erros_ingestao")
    conn.execute("DELETE FROM galpao.dispositivos WHERE id NOT IN ('esp01', 'esp02')")
    conn.execute("UPDATE galpao.dispositivos SET ativo = true, data_alojamento = NULL, faixa_manual_id = NULL")
    conn.execute("DELETE FROM galpao.faixas_itgu")
    conn.execute("TRUNCATE galpao.usuarios RESTART IDENTITY")
    conn.execute(
        # senha_alterada_em no passado: tokens emitidos "10 s atrás" nos testes ainda valem
        "INSERT INTO galpao.usuarios (email, nome, senha_hash, perfil, senha_alterada_em) VALUES "
        "('admin@teste.com', 'Admin', %s, 'admin', now() - interval '1 minute'), "
        "('leitor@teste.com', 'Leitor', %s, 'leitor', now() - interval '1 minute')",
        (HASH, HASH),
    )
    monkeypatch.setenv("DATABASE_URL", URL)
    with TestClient(app) as c:
        yield c


def cab(usuario_id, perfil, agora=None):
    return {"Authorization": f"Bearer {criar_token(usuario_id, perfil, agora)}"}


ADMIN = lambda: cab(1, "admin")  # noqa: E731
LEITOR = lambda: cab(2, "leitor")  # noqa: E731


def faixa_json(nome, inicio, fim, cmin=65, min_=70, max_=77, cmax=82):
    return {"nome": nome, "idade_inicio_dias": inicio, "idade_fim_dias": fim,
            "critico_min": cmin, "conforto_min": min_, "conforto_max": max_, "critico_max": cmax}


def criar_faixa(client, nome, inicio, fim, **limites):
    r = client.post("/faixas", json=faixa_json(nome, inicio, fim, **limites), headers=ADMIN())
    assert r.status_code == 201, r.text
    return r.json()


def inserir_leitura(conn, device_id, itgu, ts=None):
    ts = ts or AGORA()
    conn.execute(
        "INSERT INTO galpao.leituras (device_id, ts, ts_origem, t_int, ur_int, t_globo, tpo, itgu, payload) "
        "VALUES (%s, %s, 'esp', 30, 70, 32, 24, %s, '{}')",
        (device_id, ts, itgu),
    )


def alojar(client, device_id, dias_atras, **extra):
    data = (hoje_recife() - timedelta(days=dias_atras)).isoformat()
    return client.patch(f"/dispositivos/{device_id}", json={"data_alojamento": data, **extra}, headers=ADMIN())


# ---------- migração ----------

def test_004_idempotente_e_sem_btree_gist(conn):
    sql = (DB / "004_faixas_itgu.sql").read_text(encoding="utf-8")
    conn.execute(sql)
    conn.execute(sql)
    # a constraint de exclusão com range funciona sem a extensão btree_gist
    assert conn.execute("SELECT count(*) FROM pg_extension WHERE extname = 'btree_gist'").fetchone()[0] == 0


# ---------- faixas: permissões e CRUD ----------

def test_leitor_lista_mas_nao_cria(client):
    criar_faixa(client, "Semana 1", 0, 7)
    r = client.get("/faixas", headers=LEITOR())
    assert r.status_code == 200 and len(r.json()) == 1
    r = client.post("/faixas", json=faixa_json("X", 8, 14), headers=LEITOR())
    assert r.status_code == 403
    assert client.patch("/faixas/1", json={"nome": "Y"}, headers=LEITOR()).status_code == 403
    assert client.get("/faixas").status_code == 401


def test_criar_e_listar_ordenado(client):
    criar_faixa(client, "Semana 2", 8, 14)
    f1 = criar_faixa(client, "Semana 1", 0, 7)
    assert f1["ativo"] is True and f1["conforto_min"] == 70 and "criado_em" in f1
    nomes = [f["nome"] for f in client.get("/faixas", headers=LEITOR()).json()]
    assert nomes == ["Semana 1", "Semana 2"]  # por idade_inicio_dias


@pytest.mark.parametrize("corpo", [
    faixa_json("x", 0, 7, cmin=70, min_=65),       # critico_min > conforto_min
    faixa_json("x", 0, 7, min_=77, max_=77),       # conforto_min == conforto_max
    faixa_json("x", 0, 7, max_=82, cmax=82),       # conforto_max == critico_max
    faixa_json("x", 0, 7, min_=78),                # conforto_min > conforto_max
    faixa_json("x", 10, 5),                        # fim < início
    faixa_json("x", -1, 5),                        # idade negativa
    faixa_json("", 0, 7),                          # nome vazio
])
def test_faixa_invalida_422(client, corpo):
    assert client.post("/faixas", json=corpo, headers=ADMIN()).status_code == 422


def test_sobreposicao_com_ativa_409(client):
    criar_faixa(client, "A", 8, 14)
    for ini, fim in [(8, 14), (10, 20), (0, 8), (14, 30), (9, 10)]:
        assert client.post("/faixas", json=faixa_json("B", ini, fim), headers=ADMIN()).status_code == 409
    criar_faixa(client, "C", 15, 20)  # encostando (sem sobrepor) pode


def test_sobreposicao_com_inativa_permitida(client):
    a = criar_faixa(client, "A", 8, 14)
    assert client.patch(f"/faixas/{a['id']}", json={"ativo": False}, headers=ADMIN()).status_code == 200
    criar_faixa(client, "B", 8, 14)  # mesma idade, a antiga está inativa
    # reativar a antiga sobreporia a nova
    r = client.patch(f"/faixas/{a['id']}", json={"ativo": True}, headers=ADMIN())
    assert r.status_code == 409


def test_patch_que_sobrepoe_409(client):
    criar_faixa(client, "A", 8, 14)
    b = criar_faixa(client, "B", 15, 20)
    r = client.patch(f"/faixas/{b['id']}", json={"idade_inicio_dias": 12}, headers=ADMIN())
    assert r.status_code == 409
    # sem alterar nada no banco
    assert [f["idade_inicio_dias"] for f in client.get("/faixas", headers=LEITOR()).json()] == [8, 15]


def test_patch_valida_com_os_valores_atuais(client):
    f = criar_faixa(client, "A", 0, 7)  # conforto 70–77
    # só conforto_min = 78 (> conforto_max atual) deve falhar
    assert client.patch(f"/faixas/{f['id']}", json={"conforto_min": 78}, headers=ADMIN()).status_code == 422
    # fim < início atual
    assert client.patch(f"/faixas/{f['id']}", json={"idade_fim_dias": 0, "idade_inicio_dias": 3}, headers=ADMIN()).status_code == 422
    # alteração coerente passa
    r = client.patch(f"/faixas/{f['id']}", json={"conforto_min": 71, "nome": "Nova"}, headers=ADMIN())
    assert r.status_code == 200 and r.json()["conforto_min"] == 71 and r.json()["nome"] == "Nova"


def test_patch_faixa_inexistente_e_vazio(client):
    assert client.patch("/faixas/999", json={"nome": "x"}, headers=ADMIN()).status_code == 404
    f = criar_faixa(client, "A", 0, 7)
    assert client.patch(f"/faixas/{f['id']}", json={}, headers=ADMIN()).status_code == 422


def test_desativar_faixa_em_uso_manual_409(client):
    f = criar_faixa(client, "A", 0, 7)
    assert client.patch("/dispositivos/esp01", json={"faixa_manual_id": f["id"]}, headers=ADMIN()).status_code == 200
    r = client.patch(f"/faixas/{f['id']}", json={"ativo": False}, headers=ADMIN())
    assert r.status_code == 409 and "esp01" in r.json()["detail"]
    # liberando o dispositivo, pode desativar
    client.patch("/dispositivos/esp01", json={"faixa_manual_id": None}, headers=ADMIN())
    assert client.patch(f"/faixas/{f['id']}", json={"ativo": False}, headers=ADMIN()).status_code == 200


# ---------- dispositivos: alojamento, faixa manual e situação ----------

def test_ultima_com_idade_e_classificacao(client, conn):
    f = criar_faixa(client, "Semana 2", 8, 14)
    criar_faixa(client, "Semana 1", 0, 7, cmin=60, min_=65, max_=72, cmax=80)
    assert alojar(client, "esp01", 10).status_code == 200

    esperado = [(75.0, "conforto"), (78.0, "alerta"), (69.0, "alerta"), (83.0, "critico"), (64.0, "critico")]
    for i, (itgu, classe) in enumerate(esperado):
        inserir_leitura(conn, "esp01", itgu, AGORA() + timedelta(seconds=i))
        corpo = client.get("/dispositivos/esp01/ultima", headers=LEITOR()).json()
        sit = corpo["situacao"]
        assert sit["idade_dias"] == 10 and sit["origem_faixa"] == "idade"
        assert sit["faixa"] == {"id": f["id"], "nome": "Semana 2", "critico_min": 65, "conforto_min": 70,
                                "conforto_max": 77, "critico_max": 82}
        assert sit["classificacao"] == classe


def test_situacao_sem_leitura_e_sem_faixa(client, conn):
    # sem data e sem faixa: sem_faixa se houver leitura; null se não houver
    sit = client.get("/dispositivos/esp01/ultima", headers=LEITOR()).json()["situacao"]
    assert sit == {"idade_dias": None, "origem_faixa": None, "faixa": None, "classificacao": None}
    inserir_leitura(conn, "esp01", 75.0)
    sit = client.get("/dispositivos/esp01/ultima", headers=LEITOR()).json()["situacao"]
    assert sit["classificacao"] == "sem_faixa"
    # idade fora de qualquer faixa
    criar_faixa(client, "A", 0, 7)
    alojar(client, "esp01", 30)
    sit = client.get("/dispositivos/esp01/ultima", headers=LEITOR()).json()["situacao"]
    assert sit["idade_dias"] == 30 and sit["faixa"] is None and sit["classificacao"] == "sem_faixa"


def test_faixa_manual_sobrepoe_a_idade(client, conn):
    criar_faixa(client, "A", 0, 7)
    b = criar_faixa(client, "B", 8, 14, cmin=50, min_=55, max_=60, cmax=65)
    alojar(client, "esp01", 3)  # idade 3 -> faixa A; manual aponta para B
    r = client.patch("/dispositivos/esp01", json={"faixa_manual_id": b["id"]}, headers=ADMIN())
    assert r.status_code == 200 and r.json()["faixa_manual_id"] == b["id"]
    inserir_leitura(conn, "esp01", 58.0)
    sit = client.get("/dispositivos/esp01/ultima", headers=LEITOR()).json()["situacao"]
    assert sit["origem_faixa"] == "manual" and sit["faixa"]["id"] == b["id"]
    assert sit["idade_dias"] == 3 and sit["classificacao"] == "conforto"


def test_faixa_manual_invalida_422(client):
    f = criar_faixa(client, "A", 0, 7)
    client.patch(f"/faixas/{f['id']}", json={"ativo": False}, headers=ADMIN())
    for faixa_id in (f["id"], 999):  # inativa e inexistente
        r = client.patch("/dispositivos/esp01", json={"faixa_manual_id": faixa_id}, headers=ADMIN())
        assert r.status_code == 422


def test_data_alojamento_futura_422(client):
    amanha = (hoje_recife() + timedelta(days=1)).isoformat()
    assert client.patch("/dispositivos/esp01", json={"data_alojamento": amanha}, headers=ADMIN()).status_code == 422
    hoje = hoje_recife().isoformat()
    r = client.patch("/dispositivos/esp01", json={"data_alojamento": hoje}, headers=ADMIN())
    assert r.status_code == 200 and r.json()["data_alojamento"] == hoje  # hoje pode: idade 0
    r = client.patch("/dispositivos/esp01", json={"data_alojamento": None}, headers=ADMIN())
    assert r.json()["data_alojamento"] is None


def test_dispositivos_trazem_situacao_para_todos(client, conn):
    criar_faixa(client, "A", 0, 7)
    alojar(client, "esp01", 2)
    inserir_leitura(conn, "esp01", 73.0)
    lista = client.get("/dispositivos", headers=LEITOR()).json()
    assert len(lista) == 2
    por_id = {d["id"]: d for d in lista}
    assert all("situacao" in d for d in lista)
    assert por_id["esp01"]["situacao"]["classificacao"] == "conforto"
    assert por_id["esp01"]["situacao"]["idade_dias"] == 2
    assert por_id["esp01"]["data_alojamento"] == (hoje_recife() - timedelta(days=2)).isoformat()
    assert por_id["esp02"]["situacao"] == {"idade_dias": None, "origem_faixa": None, "faixa": None, "classificacao": None}


# ---------- invalidação de token na troca de senha ----------

def test_admin_redefine_senha_derruba_token_antigo(client):
    antigo = cab(2, "leitor", AGORA() - timedelta(seconds=10))
    assert client.get("/auth/me", headers=antigo).status_code == 200
    assert client.post("/usuarios/2/senha", json={"senha": "outra-senha-456"}, headers=ADMIN()).status_code == 204
    assert client.get("/auth/me", headers=antigo).status_code == 401
    # login logo depois (mesmo segundo da troca) funciona
    r = client.post("/auth/login", data={"username": "leitor@teste.com", "password": "outra-senha-456"})
    assert r.status_code == 200
    novo = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get("/auth/me", headers=novo).status_code == 200


def test_trocar_propria_senha_devolve_token_novo_e_invalida_o_antigo(client):
    antigo = cab(2, "leitor", AGORA() - timedelta(seconds=10))
    r = client.post("/auth/senha", json={"senha_atual": SENHA, "senha_nova": "senha-trocada-789"}, headers=antigo)
    assert r.status_code == 200
    assert r.json()["token_type"] == "bearer"
    novo = {"Authorization": f"Bearer {r.json()['access_token']}"}

    assert client.get("/auth/me", headers=antigo).status_code == 401  # token antigo morreu
    assert client.get("/auth/me", headers=novo).status_code == 200  # o devolvido funciona, já no mesmo segundo
    # login com a senha nova, também no mesmo segundo
    assert client.post("/auth/login", data={"username": "leitor@teste.com", "password": "senha-trocada-789"}).status_code == 200
    assert client.post("/auth/login", data={"username": "leitor@teste.com", "password": SENHA}).status_code == 401


def test_token_sem_troca_de_senha_continua_valido(client):
    assert client.get("/auth/me", headers=LEITOR()).status_code == 200
