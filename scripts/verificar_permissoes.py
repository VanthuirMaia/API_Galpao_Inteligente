"""Verifica as permissões das roles galpao_ingestor e galpao_leitura.

Uso: python scripts/verificar_permissoes.py --ingestor URL --leitura URL
Sai com código != 0 se algum item falhar.
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ingestor"))
from processamento import novo_cache, processar_mensagem  # noqa: E402

MARCA = "verificar_permissoes"  # marca nos registros de teste, para limpeza
falhas = 0


def item(nome: str, ok: bool, detalhe: str = "") -> None:
    global falhas
    falhas += 0 if ok else 1
    print(f"{'OK   ' if ok else 'FALHA'} {nome}" + (f" ({detalhe})" if detalhe else ""))


def deve_ser_negado(conn, nome: str, sql: str) -> None:
    """Executa o SQL e espera erro de permissão negada."""
    try:
        conn.execute(sql)
        item(nome, False, "executou, deveria ter sido negado")
    except psycopg.errors.InsufficientPrivilege:
        item(nome, True, "permissão negada")
    except psycopg.Error as e:
        item(nome, False, f"erro diferente do esperado: {e}")


def payload(device: str, ts: int) -> bytes:
    return json.dumps({
        "device_id": device, "ts": ts, "teste": MARCA,
        "interno": {"t": 30, "ur": 70}, "globo": {"t": 32},
    }).encode()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ingestor", required=True, help="URL do Postgres com a role galpao_ingestor")
    ap.add_argument("--leitura", required=True, help="URL do Postgres com a role galpao_leitura")
    args = ap.parse_args()

    agora = datetime.now(timezone.utc)
    ts = int(agora.timestamp())
    cache = novo_cache()

    print("== galpao_ingestor")
    with psycopg.connect(args.ingestor, autocommit=True) as conn:
        msg = payload("esp01", ts)
        r = processar_mensagem(conn, cache, "galpao/esp01/leituras", msg, agora)
        item("processar_mensagem válida -> gravada", r == "gravada", r)
        r = processar_mensagem(conn, cache, "galpao/esp01/leituras", msg, agora)
        item("mesma mensagem -> duplicada", r == "duplicada", r)
        r = processar_mensagem(conn, cache, "galpao/esp99/leituras", payload("esp99", ts), agora)
        item("esp99 -> rejeitada:device_desconhecido", r == "rejeitada:device_desconhecido", r)
        deve_ser_negado(conn, "DELETE em galpao.leituras negado", "DELETE FROM galpao.leituras")

    print("== galpao_leitura")
    with psycopg.connect(args.leitura, autocommit=True) as conn:
        try:
            n = conn.execute("SELECT count(*) FROM galpao.leituras").fetchone()[0]
            item("SELECT em galpao.leituras", True, f"{n} linhas")
        except psycopg.Error as e:
            item("SELECT em galpao.leituras", False, str(e))
        deve_ser_negado(
            conn, "INSERT em galpao.leituras negado",
            "INSERT INTO galpao.leituras (device_id, ts, ts_origem, t_int, ur_int, t_globo, tpo, itgu, payload) "
            "VALUES ('esp01', now(), 'esp', 1, 1, 1, 1, 1, '{}')",
        )

    print()
    print("Ficaram registros de teste (esp01 em galpao.leituras, esp99 em galpao.erros_ingestao).")
    print("As roles de aplicação não têm DELETE; o admin remove com:")
    print(f"  DELETE FROM galpao.leituras WHERE payload->>'teste' = '{MARCA}';")
    print(f"  DELETE FROM galpao.erros_ingestao WHERE payload LIKE '%{MARCA}%';")

    sys.exit(1 if falhas else 0)


if __name__ == "__main__":
    main()
