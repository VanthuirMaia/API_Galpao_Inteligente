"""GET /previsao: ITGU previsto para daqui a 30 min.

As features vêm do mesmo código do treino (ml/features.py, copiado para a imagem em /srv/ml)
e o modelo vem de MODELO_DIR (ml/modelo, montado como volume). Aqui só entra o que é da API:
buscar as leituras, classificar pela faixa vigente e montar a resposta.
"""
from datetime import datetime, timedelta, timezone

import pandas as pd
from fastapi import APIRouter, Depends, Query

from app import config
from app.classificacao import classificar, escolher_faixa, hoje_recife
from app.deps import get_conn, usuario_atual
from app.modelos import PrevisaoOut
from app.rotas_dispositivos import exigir_dispositivo
from app.rotas_faixas import carregar_faixas_ativas

# código compartilhado com o treino (ml/): vive em /srv/ml no container e em ml/ no repositório
from features import features_ao_vivo, inicio_da_consulta
from modelo_io import carregar_modelo, prever

router = APIRouter(prefix="/previsao", tags=["previsao"], dependencies=[Depends(usuario_atual)])

VARIAVEIS = ["t_int", "ur_int", "t_globo", "t_ext", "ur_ext", "tpo", "itgu"]

SQL_LEITURAS = f"""
    SELECT ts, {", ".join(VARIAVEIS)} FROM galpao.leituras
    WHERE device_id = %(device_id)s AND ts >= %(inicio)s AND ts <= %(fim)s
    ORDER BY ts
"""


def buscar_leituras(conn, device_id: str, inicio: pd.Timestamp, fim: pd.Timestamp) -> pd.DataFrame:
    """Leituras brutas do período em DataFrame (ts em UTC, variáveis em float; nulo vira NaN)."""
    linhas = conn.execute(
        SQL_LEITURAS, {"device_id": device_id, "inicio": inicio.to_pydatetime(), "fim": fim.to_pydatetime()}
    ).fetchall()
    df = pd.DataFrame(linhas, columns=["ts", *VARIAVEIS])
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df[VARIAVEIS] = df[VARIAVEIS].astype("float64")
    return df


@router.get("", response_model=PrevisaoOut)
def previsao(device_id: str = Query(..., description="id do dispositivo, ex.: esp01"), conn=Depends(get_conn)):
    dispositivo = exigir_dispositivo(conn, device_id)
    agora = pd.Timestamp(datetime.now(timezone.utc))
    base = {"device_id": device_id, "gerado_em": agora.to_pydatetime()}

    modelo = carregar_modelo(config.modelo_dir())
    if modelo is None:
        return {**base, "status": "modelo_indisponivel", "motivo": "nenhum modelo treinado instalado"}
    meta = modelo["meta"]

    bruto = buscar_leituras(conn, device_id, inicio_da_consulta(agora), agora)
    X, motivo = features_ao_vivo(bruto, agora)
    if X is None:
        return {**base, "status": "dados_insuficientes", "motivo": motivo}
    faltam = [f for f in meta["features"] if f not in X.columns or X[f].isna().any()]
    if faltam:
        return {**base, "status": "dados_insuficientes", "motivo": f"sem dados de: {', '.join(faltam[:4])}"}

    previsto = round(float(prever(modelo, X)[0]), 2)
    faixa, _, _ = escolher_faixa(dispositivo, carregar_faixas_ativas(conn), hoje_recife())
    referencia = X.index[0]
    return {
        **base,
        "status": "ok",
        "itgu_atual": float(bruto["itgu"].iloc[-1]),
        "itgu_previsto": previsto,
        "horizonte_min": meta["horizonte_min"],
        "classificacao": classificar(previsto, faixa),
        "referencia_ts": referencia.to_pydatetime(),
        "previsto_para": (referencia + timedelta(minutes=meta["horizonte_min"])).to_pydatetime(),
        "modelo": meta["tipo"],
        "origem": meta["origem"],
        "mae_teste": round(meta["mae_teste"], 3),
        "treinado_em": meta["treinado_em"],
    }
