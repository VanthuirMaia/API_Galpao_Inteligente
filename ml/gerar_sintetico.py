"""Gera um CSV SINTÉTICO com as mesmas colunas do export bruto de /leituras/csv.

Galpão com telhado de zinco no Agreste: mínimo de madrugada, pico à tarde,
ITGU passando de 80 em algumas tardes. Serve só para testar o pipeline:
os números gerados NÃO são resultado do projeto.

Uso: uv run python gerar_sintetico.py [--saida dados/galpao_SINTETICO_10dias.csv]
"""
import argparse
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# colunas e ordem idênticas ao export bruto da API (COLUNAS_LEITURA)
COLUNAS = ["ts", "ts_origem", "recebido_em", "t_int", "ur_int", "t_globo",
           "t_ext", "ur_ext", "tpo", "itgu", "rssi"]

MAGNUS_A, MAGNUS_B = 17.62, 243.12
DIAS = 10
INICIO_UTC = pd.Timestamp("2026-12-01 03:00:00", tz="UTC")  # 00:00 em Recife (UTC-3)
# buracos (dia, hora local de início, duração em horas)
BURACOS = [(3, 9.0, 3.0), (7, 20.0, 4.0)]
LEITURAS_SERVIDOR_APOS_BURACO = 10  # ESP reiniciou sem NTP: ts = recebido_em


def ponto_orvalho(t, ur):
    """Magnus (Sonntag), igual ao ingestor/itgu.py."""
    g = np.log(ur / 100) + (MAGNUS_A * t) / (MAGNUS_B + t)
    return MAGNUS_B * g / (MAGNUS_A - g)


def ur_de_orvalho(t, td):
    """Inverso do Magnus: UR (%) a partir da temperatura e do ponto de orvalho."""
    return 100 * np.exp(MAGNUS_A * td / (MAGNUS_B + td) - MAGNUS_A * t / (MAGNUS_B + t))


def suavizar(x, tau_min):
    """Filtro de 1ª ordem (inércia térmica), passo de 1 min."""
    a = 1 / tau_min
    y = np.empty_like(x)
    y[0] = x[0]
    for i in range(1, len(x)):
        y[i] = y[i - 1] + a * (x[i] - y[i - 1])
    return y


def ruido_ar1(rng, n, desvio, fi=0.95):
    """Ruído autocorrelacionado (variação lenta de clima)."""
    e = rng.normal(0, desvio * math.sqrt(1 - fi**2), n)
    r = np.zeros(n)
    for i in range(1, n):
        r[i] = fi * r[i - 1] + e[i]
    return r


def gerar(semente=42):
    rng = np.random.default_rng(semente)
    n = DIAS * 24 * 60
    ts = INICIO_UTC + pd.to_timedelta(np.arange(n), unit="min")
    hora = ((ts.tz_convert("America/Recife").hour + ts.tz_convert("America/Recife").minute / 60)
            .to_numpy())
    dia = (np.arange(n) // 1440)

    # fator de radiação de cada dia: dias nublados (~0,5) e limpos (~1,0)
    fator_dia = np.clip(rng.uniform(0.3, 1.0, DIAS), 0, 1)
    fator = fator_dia[dia]

    sol = np.where((hora > 6) & (hora < 18), np.sin(np.pi * (hora - 6) / 12), 0.0) * fator
    forma = 0.5 * (1 + np.cos(2 * np.pi * (hora - 14.5) / 24))  # pico às 14h30

    t_ext = 21 + 9 * forma * (0.6 + 0.4 * fator) + ruido_ar1(rng, n, 0.6) + rng.normal(0, 0.15, n)
    # zinco: o ar interno e sobretudo o globo esquentam acima do ar externo
    t_int = suavizar(t_ext + 2.5 * sol, 40) + rng.normal(0, 0.1, n)
    t_globo = suavizar(t_ext + 0.8 + 5.5 * sol, 35) + rng.normal(0, 0.12, n)

    td = 18 + ruido_ar1(rng, n, 1.0) - 1.5 * sol  # ponto de orvalho: varia devagar
    ur_int = np.clip(ur_de_orvalho(t_int, td) + rng.normal(0, 0.5, n), 25, 99)
    ur_ext = np.clip(ur_de_orvalho(t_ext, td - 0.5) + rng.normal(0, 0.8, n), 25, 99)

    tpo = ponto_orvalho(t_int, ur_int)
    itgu = t_globo + 0.36 * tpo + 41.5

    # segundo exato da leitura varia um pouco; recebido_em chega 1-3 s depois
    ts_leitura = ts + pd.to_timedelta(rng.integers(0, 4, n), unit="s")
    recebido = ts_leitura + pd.to_timedelta(rng.integers(1, 4, n), unit="s")
    origem = np.array(["esp"] * n, dtype=object)

    df = pd.DataFrame({
        "ts": ts_leitura, "ts_origem": origem, "recebido_em": recebido,
        "t_int": t_int.round(2), "ur_int": ur_int.round(2), "t_globo": t_globo.round(2),
        "t_ext": t_ext.round(2), "ur_ext": ur_ext.round(2),
        "tpo": tpo.round(2), "itgu": itgu.round(2),
        "rssi": np.clip(rng.normal(-62, 3, n).round(), -90, -40).astype(int),
    })

    # 10 leituras após cada buraco vêm sem NTP: ts = recebido_em
    remover = np.zeros(n, dtype=bool)
    for d, h_ini, dur in BURACOS:
        ini = d * 1440 + int(h_ini * 60)
        fim = ini + int(dur * 60)
        remover[ini:fim] = True
        idx = np.arange(fim, fim + LEITURAS_SERVIDOR_APOS_BURACO)
        df.loc[idx, "ts_origem"] = "servidor"
        df.loc[idx, "ts"] = df.loc[idx, "recebido_em"]
    df = df[~remover].reset_index(drop=True)
    return df[COLUNAS]


def gravar_csv(df, caminho):
    """Mesmo formato do export: ISO 8601 UTC, vazio para nulo, \\n, sem índice."""
    saida = df.copy()
    for c in ("ts", "recebido_em"):
        saida[c] = saida[c].map(lambda v: v.isoformat())
    Path(caminho).parent.mkdir(parents=True, exist_ok=True)
    saida.to_csv(caminho, index=False, lineterminator="\n")


def main():
    sys.stdout.reconfigure(encoding="utf-8")  # acentos no console do Windows
    pasta = Path(__file__).parent
    ap = argparse.ArgumentParser(description="Gera CSV sintético de leituras do galpão.")
    ap.add_argument("--saida", default=str(pasta / "dados" / "galpao_SINTETICO_10dias.csv"))
    ap.add_argument("--semente", type=int, default=42)
    args = ap.parse_args()
    df = gerar(args.semente)
    gravar_csv(df, args.saida)
    print(f"{len(df)} leituras SINTÉTICAS gravadas em {args.saida} "
          f"(ITGU máx {df['itgu'].max():.1f})")


if __name__ == "__main__":
    main()
