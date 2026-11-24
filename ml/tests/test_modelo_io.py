"""Salvar/carregar/prever (JSON), recarga automática e trava contra sobrescrever modelo real."""
import json
import os

import numpy as np
import pandas as pd
import pytest

import modelo_io
from features import montar_features
from gerar_sintetico import gerar
from preparar import agregar_5min, segmentar
from rodar import salvar_melhor_modelo
from treinar import treinar


@pytest.fixture(scope="module")
def treinado():
    df = gerar(semente=3)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    seg, _ = segmentar(agregar_5min(df))
    X, y = montar_features(seg)
    return X, treinar(X, y)


@pytest.mark.parametrize("tipo", ["linear", "xgboost"])
def test_ida_e_volta_preserva_previsoes(tmp_path, treinado, tipo):
    X, res = treinado
    estimador = res["modelos"][tipo]
    modelo_io.salvar_modelo(tmp_path, tipo, estimador, {"features": list(X.columns), "origem": "sintetico"})
    carregado = modelo_io.carregar_modelo(tmp_path)
    amostra = X.iloc[-50:]
    np.testing.assert_allclose(modelo_io.prever(carregado, amostra), estimador.predict(amostra), rtol=1e-5, atol=1e-5)
    assert carregado["meta"]["tipo"] == tipo and carregado["meta"]["origem"] == "sintetico"


def test_recarrega_quando_o_modelo_muda_e_apaga_o_antigo(tmp_path, treinado):
    X, res = treinado
    meta = {"features": list(X.columns), "origem": "sintetico"}
    modelo_io.salvar_modelo(tmp_path, "linear", res["modelos"]["linear"], meta)
    primeiro = modelo_io.carregar_modelo(tmp_path)
    assert modelo_io.carregar_modelo(tmp_path) is primeiro  # em cache

    antigo = primeiro["meta"]["arquivo_modelo"]
    os.utime(tmp_path / "metadados.json", ns=(1, 1))  # garante mtime diferente do próximo salvamento
    modelo_io.carregar_modelo(tmp_path)
    novo_meta = modelo_io.salvar_modelo(tmp_path, "xgboost", res["modelos"]["xgboost"], {**meta, "origem": "real"})
    segundo = modelo_io.carregar_modelo(tmp_path)
    assert segundo["meta"]["origem"] == "real" and segundo["meta"]["tipo"] == "xgboost"
    if novo_meta["arquivo_modelo"] != antigo:
        assert not (tmp_path / antigo).exists()


def test_sem_modelo_devolve_none(tmp_path):
    assert modelo_io.carregar_modelo(tmp_path / "nao_existe") is None


def test_modelo_sintetico_nao_substitui_real(tmp_path):
    (tmp_path / "metadados.json").write_text(json.dumps({"origem": "real"}), encoding="utf-8")
    with pytest.raises(SystemExit):
        salvar_melhor_modelo(tmp_path, False, "sintetico", "x.csv", None, None, [])
