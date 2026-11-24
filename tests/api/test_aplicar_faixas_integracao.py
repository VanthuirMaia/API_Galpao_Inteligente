"""scripts/aplicar_faixas_poedeiras.py com Postgres real (DATABASE_URL_TEST)."""
import os
from pathlib import Path

import pytest

URL = os.environ.get("DATABASE_URL_TEST")
if not URL:
    pytest.skip("DATABASE_URL_TEST não definida", allow_module_level=True)

import psycopg

from aplicar_faixas_poedeiras import FAIXAS, aplicar_faixas

DB = Path(__file__).parent.parent.parent / "db"
INSERT = (
    "INSERT INTO galpao.faixas_itgu (nome, idade_inicio_dias, idade_fim_dias, critico_min, conforto_min, "
    "conforto_max, critico_max) VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id"
)


@pytest.fixture
def conn():
    with psycopg.connect(URL, autocommit=True) as c:
        for arq in ("001_init.sql", "002_permissoes.sql", "003_usuarios_api.sql", "004_faixas_itgu.sql", "005_faixas_limites_opcionais.sql"):
            c.execute((DB / arq).read_text(encoding="utf-8"))
        c.execute("UPDATE galpao.dispositivos SET faixa_manual_id = NULL")
        c.execute("DELETE FROM galpao.faixas_itgu")
        yield c
        c.execute("UPDATE galpao.dispositivos SET faixa_manual_id = NULL")
        c.execute("DELETE FROM galpao.faixas_itgu")


def ativas(conn):
    return conn.execute("SELECT nome FROM galpao.faixas_itgu WHERE ativo ORDER BY idade_inicio_dias").fetchall()


def test_cria_as_faixas_e_desativa_as_de_exemplo(conn):
    exemplo = conn.execute(INSERT, ("EXEMPLO - Semana 1", 0, 7, 70, 74, 79, 84)).fetchone()[0]
    conn.execute("UPDATE galpao.dispositivos SET faixa_manual_id = %s WHERE id = 'esp01'", (exemplo,))

    resultado = aplicar_faixas(conn)

    assert resultado["desativadas"] == 1 and len(resultado["criadas"]) == len(FAIXAS)
    assert [n for (n,) in ativas(conn)] == [f[0] for f in FAIXAS]
    # a EXEMPLO continua no banco, só inativa; a faixa manual que apontava para ela foi solta
    assert conn.execute("SELECT ativo FROM galpao.faixas_itgu WHERE id = %s", (exemplo,)).fetchone()[0] is False
    assert conn.execute("SELECT faixa_manual_id FROM galpao.dispositivos WHERE id = 'esp01'").fetchone()[0] is None
    # limites inexistentes ficam nulos
    adulta = conn.execute(
        "SELECT critico_min, conforto_min, conforto_max, critico_max, idade_inicio_dias, idade_fim_dias "
        "FROM galpao.faixas_itgu WHERE nome LIKE '%Recria e produção%'"
    ).fetchone()
    assert adulta == (None, None, 75.0, 78.0, 43, 1000)


def test_idempotente(conn):
    aplicar_faixas(conn)
    segunda = aplicar_faixas(conn)
    assert segunda["criadas"] == [] and segunda["desativadas"] == 0 and len(segunda["mantidas"]) == len(FAIXAS)
    assert conn.execute("SELECT count(*) FROM galpao.faixas_itgu").fetchone()[0] == len(FAIXAS)


def test_nao_sobrescreve_faixa_editada_pelo_admin(conn):
    aplicar_faixas(conn)
    conn.execute("UPDATE galpao.faixas_itgu SET conforto_max = 76 WHERE nome LIKE '%Recria e produção%'")
    aplicar_faixas(conn)
    assert conn.execute("SELECT conforto_max FROM galpao.faixas_itgu WHERE nome LIKE '%Recria e produção%'").fetchone()[0] == 76


def test_conflito_de_idade_nao_altera_nada(conn):
    exemplo = conn.execute(INSERT, ("EXEMPLO - Semana 1", 0, 7, 70, 74, 79, 84)).fetchone()[0]
    conn.execute(INSERT, ("Faixa do professor", 10, 20, 60, 65, 75, 80))  # se sobrepõe à 2ª semana (8 a 14)

    with pytest.raises(ValueError, match="Faixa do professor"):
        with conn.transaction():  # a transação desfaz tudo, inclusive a desativação da EXEMPLO
            aplicar_faixas(conn)

    assert conn.execute("SELECT ativo FROM galpao.faixas_itgu WHERE id = %s", (exemplo,)).fetchone()[0] is True
    assert {n for (n,) in ativas(conn)} == {"EXEMPLO - Semana 1", "Faixa do professor"}
