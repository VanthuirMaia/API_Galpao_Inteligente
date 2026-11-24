"""Simulador ao vivo para DESENVOLVIMENTO / gravação de vídeo. Nunca use em produção.

Insere uma leitura nova de cada galpão (esp01 e esp02) a cada INTERVALO segundos, com a hora atual,
reaproveitando o gerador de gerar_dados_dev.py (mesmo ciclo diário de temperatura).
Grava direto no Postgres (não passa pelo MQTT). Pare com Ctrl+C.

Uso: DATABASE_URL=postgresql://galpao:galpao_dev@localhost:5432/galpao INTERVALO=5 python scripts/simulador_dev.py
Recusa rodar se o banco não for localhost.
"""
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gerar_dados_dev import PERFIS, exigir_localhost, leitura_sintetica  # noqa: E402

SQL = (
    "INSERT INTO galpao.leituras (device_id, ts, ts_origem, recebido_em, t_int, ur_int, t_globo, "
    "t_ext, ur_ext, tpo, itgu, rssi, payload) "
    "VALUES (%(device_id)s, %(ts)s, 'esp', %(ts)s, %(t_int)s, %(ur_int)s, %(t_globo)s, %(t_ext)s, "
    "%(ur_ext)s, %(tpo)s, %(itgu)s, %(rssi)s, %(payload)s) ON CONFLICT (device_id, ts) DO NOTHING"
)


def main() -> None:
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL não definida")
    exigir_localhost(url)
    intervalo = float(os.environ.get("INTERVALO", "5"))

    print(f"simulando {', '.join(PERFIS)} a cada {intervalo:g}s (Ctrl+C para parar)", flush=True)
    with psycopg.connect(url, autocommit=True) as conn:
        while True:
            ts = datetime.now(timezone.utc).replace(microsecond=0)
            for device_id in PERFIS:
                linha = leitura_sintetica(device_id, ts)
                conn.execute(SQL, {**linha, "payload": Jsonb({"dev": True, "simulador": True})})
                print(f"{ts:%H:%M:%S} {device_id} t_int={linha['t_int']} ur={linha['ur_int']} itgu={linha['itgu']}", flush=True)
            time.sleep(intervalo)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nparado")
