"""Features (lags + hora do dia) e alvo (ITGU daqui a 30 min). Nenhum lag atravessa buraco.

É a ÚNICA implementação das features: o treino (rodar.py) e a API (/previsao) usam este arquivo.
"""
import numpy as np
import pandas as pd

from preparar import BURACO_MAX, PASSO, agregar_5min, descartar_janela_em_andamento, segmentar

PASSO_MIN = 5
LAGS_MIN = [5, 10, 15, 30, 60]
HORIZONTE_MIN = 30
FUSO_LOCAL = "America/Recife"  # os dados vêm em UTC; o ciclo diário é no horário local

# previsão ao vivo: lê os últimos 90 min e exige a janela atual + os lags até 60 min
JANELA_CONSULTA_MIN = 90
MIN_JANELAS = max(LAGS_MIN) // PASSO_MIN + 1


def montar_X(df):
    """df segmentado (preparar.segmentar) -> X com todas as linhas.

    Como cada segmento tem grade contínua de 5 min, shift(k) dentro do grupo
    equivale a k*5 min atrás. Linhas sem lag completo ficam com NaN.
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

    _checar_sem_buraco(X[X.notna().all(axis=1)], df)
    return X


def montar_features(df):
    """Treino: (X, y), com y = ITGU daqui a 30 min. Descarta linhas sem lag ou sem alvo."""
    X = montar_X(df)
    y = df.groupby("segmento_id")["itgu"].shift(-HORIZONTE_MIN // PASSO_MIN).rename("itgu_alvo")
    validas = X.notna().all(axis=1) & y.notna()
    return X[validas], y[validas]


def _checar_sem_buraco(X, df):
    """Garante que o lag de 60 min cai exatamente 60 min antes (sem cruzar buraco)."""
    if X.empty:
        return
    atras = df["itgu"].reindex(X.index - pd.Timedelta(minutes=max(LAGS_MIN)))
    if not np.allclose(atras.to_numpy(), X[f"itgu_lag{max(LAGS_MIN)}min"].to_numpy()):
        raise RuntimeError("lag atravessou um buraco: erro na montagem das features")


def inicio_da_consulta(agora):
    """Início (alinhado a 5 min) das leituras a buscar: evita uma primeira janela cortada."""
    return (agora - pd.Timedelta(minutes=JANELA_CONSULTA_MIN)).floor("5min")


def features_ao_vivo(bruto, agora):
    """Leituras brutas recentes -> (X da última janela completa, motivo).

    `bruto`: DataFrame com `ts` (UTC) e as variáveis, de inicio_da_consulta(agora) até agora.
    Mesmo caminho do treino (agregar_5min, segmentar, montar_X). Sem dados suficientes
    devolve (None, motivo em português).
    """
    if bruto.empty:
        return None, f"sem leituras nos últimos {JANELA_CONSULTA_MIN} min"
    agr = agregar_5min(bruto)
    agr = descartar_janela_em_andamento(agr, agora)
    if agr.empty:
        return None, "sem janela de 5 min completa ainda"

    atraso = agora - (agr.index[-1] + PASSO)
    if atraso > BURACO_MAX:
        return None, f"última leitura há {int(atraso.total_seconds() // 60)} min (limite {int(BURACO_MAX.total_seconds() // 60)} min)"

    df, _ = segmentar(agr)
    ultimo = df[df["segmento_id"] == df["segmento_id"].iloc[-1]]
    if len(ultimo) < MIN_JANELAS:
        return None, f"dados contínuos: {len(ultimo) * PASSO_MIN} de {max(LAGS_MIN) + PASSO_MIN} min necessários"

    X = montar_X(df).iloc[[-1]]
    return X, None
