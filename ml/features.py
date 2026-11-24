"""Features (lags + hora do dia) e alvo (ITGU daqui a 30 min). Nenhum lag atravessa buraco."""
import numpy as np
import pandas as pd

PASSO_MIN = 5
LAGS_MIN = [5, 10, 15, 30, 60]
HORIZONTE_MIN = 30
FUSO_LOCAL = "America/Recife"  # os dados vêm em UTC; o ciclo diário é no horário local


def montar_features(df):
    """df segmentado (preparar.segmentar) -> (X, y).

    Como cada segmento tem grade contínua de 5 min, shift(k) dentro do grupo
    equivale a k*5 min atrás/à frente. Linhas sem lag ou sem alvo no
    segmento são descartadas.
    """
    variaveis = [c for c in df.columns if c != "segmento_id"]
    g = df.groupby("segmento_id")
    cols = {v: df[v] for v in variaveis}  # valores atuais
    for v in variaveis:
        for lag in LAGS_MIN:
            cols[f"{v}_lag{lag}min"] = g[v].shift(lag // PASSO_MIN)
    X = pd.DataFrame(cols, index=df.index)

    local = df.index.tz_convert(FUSO_LOCAL)
    hora = local.hour + local.minute / 60
    X["hora_sen"] = np.sin(2 * np.pi * hora / 24)
    X["hora_cos"] = np.cos(2 * np.pi * hora / 24)

    y = g["itgu"].shift(-HORIZONTE_MIN // PASSO_MIN).rename("itgu_alvo")

    validas = X.notna().all(axis=1) & y.notna()
    X, y = X[validas], y[validas]
    _checar_sem_buraco(X, df)
    return X, y


def _checar_sem_buraco(X, df):
    """Garante que o lag de 60 min cai exatamente 60 min antes (sem cruzar buraco)."""
    ref = df["itgu"]
    atras = ref.reindex(X.index - pd.Timedelta(minutes=max(LAGS_MIN)))
    if not np.allclose(atras.to_numpy(), X[f"itgu_lag{max(LAGS_MIN)}min"].to_numpy()):
        raise RuntimeError("lag atravessou um buraco: erro na montagem das features")
