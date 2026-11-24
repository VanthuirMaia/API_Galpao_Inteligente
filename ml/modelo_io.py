"""Salvar, carregar e aplicar o modelo em JSON (sem pickle). Compartilhado entre treino e API.

Pasta do modelo:
  metadados.json            tipo, features, horizonte, origem, MAE/RMSE, período, data do treino
  modelo_<AAAAMMDDTHHMMSS>.json   o modelo em si (XGBoost nativo ou coeficientes da regressão linear)

O metadados.json é gravado por último e aponta para o arquivo do modelo: quem lê nunca vê
metadados de um modelo e pesos de outro. A pasta nunca é substituída (só os arquivos), para
funcionar como volume montado no container.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ARQ_META = "metadados.json"
FORMATO = 1

_cache = {}  # pasta -> (mtime do metadados.json, modelo)


def _gravar_json(caminho, dados):
    """Grava num temporário e renomeia: leitor nunca pega arquivo pela metade."""
    tmp = caminho.with_name(caminho.name + ".tmp")
    tmp.write_text(json.dumps(dados, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, caminho)


def ler_metadados(pasta):
    """Metadados do modelo salvo, ou None se não houver."""
    arq = Path(pasta) / ARQ_META
    if not arq.exists():
        return None
    return json.loads(arq.read_text(encoding="utf-8"))


def salvar_modelo(pasta, tipo, estimador, metadados):
    """Grava o modelo ("linear" = Pipeline StandardScaler+LinearRegression, ou "xgboost").

    `metadados` traz o que o treino sabe (features, origem, métricas...); aqui entram
    tipo, formato, data do treino e o nome do arquivo do modelo.
    """
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    agora = datetime.now(timezone.utc)
    nome = f"modelo_{agora:%Y%m%dT%H%M%S}.json"

    if tipo == "xgboost":
        estimador.save_model(str(pasta / nome))
    elif tipo == "linear":
        escalador = estimador.named_steps["standardscaler"]
        regressao = estimador.named_steps["linearregression"]
        _gravar_json(pasta / nome, {
            "media": escalador.mean_.tolist(), "escala": escalador.scale_.tolist(),
            "coef": regressao.coef_.tolist(), "intercepto": float(regressao.intercept_),
        })
    else:
        raise ValueError(f"tipo de modelo desconhecido: {tipo}")

    anterior = ler_metadados(pasta)
    meta = {**metadados, "tipo": tipo, "formato": FORMATO, "arquivo_modelo": nome,
            "treinado_em": agora.isoformat()}
    _gravar_json(pasta / ARQ_META, meta)  # por último: troca o modelo "de uma vez"

    if anterior and anterior.get("arquivo_modelo") != nome:
        (pasta / anterior["arquivo_modelo"]).unlink(missing_ok=True)
    return meta


def carregar_modelo(pasta):
    """Modelo da pasta, ou None se não houver. Recarrega sozinho quando o metadados.json muda."""
    arq = Path(pasta) / ARQ_META
    try:
        mtime = arq.stat().st_mtime_ns
    except FileNotFoundError:
        _cache.pop(str(pasta), None)
        return None
    em_cache = _cache.get(str(pasta))
    if em_cache and em_cache[0] == mtime:
        return em_cache[1]

    meta = json.loads(arq.read_text(encoding="utf-8"))
    caminho = Path(pasta) / meta["arquivo_modelo"]
    if meta["tipo"] == "xgboost":
        # Booster (nativo) em vez de XGBRegressor: o wrapper sklearn exigiria scikit-learn na imagem da API
        from xgboost import Booster  # só importa se o modelo for XGBoost

        objeto = Booster()
        objeto.load_model(str(caminho))
    else:
        objeto = json.loads(caminho.read_text(encoding="utf-8"))
    modelo = {"meta": meta, "objeto": objeto}
    _cache[str(pasta)] = (mtime, modelo)
    return modelo


def prever(modelo, X):
    """Previsões (array) para um DataFrame com as features do modelo (a ordem é a do treino)."""
    meta, objeto = modelo["meta"], modelo["objeto"]
    X = X[meta["features"]]
    if meta["tipo"] == "xgboost":
        from xgboost import DMatrix

        return objeto.predict(DMatrix(X))
    z = (X.to_numpy(dtype=float) - np.array(objeto["media"])) / np.array(objeto["escala"])
    return z @ np.array(objeto["coef"]) + objeto["intercepto"]
