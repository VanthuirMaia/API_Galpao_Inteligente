"""Leitura do CSV bruto, agregação em 5 min e segmentação por buracos."""
import pandas as pd

# variáveis numéricas usadas no modelo (ITGU incluído)
VARIAVEIS = ["t_int", "ur_int", "t_globo", "t_ext", "ur_ext", "tpo", "itgu"]
PASSO = pd.Timedelta(minutes=5)
BURACO_MAX = pd.Timedelta(minutes=15)  # acima disso a série é quebrada


def ler_csv(caminho):
    """Lê o export bruto de /leituras/csv. Devolve (df, info).

    info traz o percentual de leituras com ts_origem = 'servidor'
    (o ts delas é a hora de chegada, não a da medição).
    """
    df = pd.read_csv(caminho)
    if "ts" not in df.columns:
        raise SystemExit("CSV sem a coluna 'ts': exporte com agregacao=bruto "
                         "(o CSV agregado tem 'janela' em vez de 'ts').")
    df["ts"] = pd.to_datetime(df["ts"], utc=True, format="ISO8601")
    df = df.sort_values("ts").drop_duplicates("ts").reset_index(drop=True)
    pct_servidor = 0.0
    if "ts_origem" in df.columns:
        pct_servidor = float((df["ts_origem"] == "servidor").mean() * 100)
    info = {"leituras_brutas": len(df), "pct_servidor": pct_servidor}
    return df, info


def agregar_5min(df):
    """Média por janela de 5 min (índice = início da janela, UTC).

    Colunas totalmente vazias (ex.: t_ext no galpão-modelo) são descartadas.
    """
    cols = [c for c in VARIAVEIS if c in df.columns]
    agr = df.assign(janela=df["ts"].dt.floor("5min")).groupby("janela")[cols].mean()
    return agr.dropna(axis=1, how="all")


def achar_buracos(janelas):
    """Buracos entre janelas consecutivas (diferença > 15 min).

    Devolve um DataFrame com inicio (última janela antes), fim (primeira depois)
    e duracao_min (tempo sem dados).
    """
    dif = janelas.to_series().diff()
    fim = janelas[(dif > BURACO_MAX).to_numpy()]
    inicio = janelas[:-1][(dif.iloc[1:] > BURACO_MAX).to_numpy()]
    out = pd.DataFrame({"inicio": inicio, "fim": fim})
    out["duracao_min"] = ((out["fim"] - out["inicio"]) - PASSO).dt.total_seconds() / 60
    return out.reset_index(drop=True)


def segmentar(agr):
    """Quebra a série nos buracos longos. Devolve (df com 'segmento_id', info).

    Dentro de um segmento a grade é contínua de 5 em 5 min: janelas faltantes
    (até 15 min) são preenchidas com o último valor. Buracos longos nunca são
    interpolados: viram fronteira entre segmentos.
    """
    seg_id = (agr.index.to_series().diff() > BURACO_MAX).cumsum()
    partes, preenchidas = [], 0
    for sid, parte in agr.groupby(seg_id.to_numpy()):
        grade = pd.date_range(parte.index[0], parte.index[-1], freq=PASSO)
        preenchidas += len(grade) - len(parte)
        parte = parte.reindex(grade).ffill()
        parte["segmento_id"] = sid
        partes.append(parte)
    df = pd.concat(partes)
    df.index.name = "janela"
    info = {
        "janelas": len(df),
        "janelas_preenchidas": preenchidas,
        "segmentos": int(df["segmento_id"].nunique()),
        "buracos": achar_buracos(agr.index),
    }
    return df, info


def preparar(caminho):
    """CSV -> série em 5 min segmentada. Devolve (df, info)."""
    bruto, info = ler_csv(caminho)
    agr = agregar_5min(bruto)
    df, info_seg = segmentar(agr)
    info.update(info_seg)
    info["inicio"], info["fim"] = df.index[0], df.index[-1]
    return df, info
