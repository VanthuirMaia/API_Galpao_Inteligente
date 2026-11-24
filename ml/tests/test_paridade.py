"""Paridade treino x ao vivo: as features calculadas só com os últimos 90 min (caminho da API)
têm de ser IGUAIS às do pipeline completo de treino, e buracos têm de virar "dados insuficientes"."""
import numpy as np
import pandas as pd
import pytest

from features import MIN_JANELAS, features_ao_vivo, inicio_da_consulta, montar_X
from gerar_sintetico import gerar
from preparar import agregar_5min, segmentar


@pytest.fixture(scope="module")
def bruto():
    """10 dias sintéticos (com 2 buracos), ts em UTC."""
    df = gerar(semente=7)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df


@pytest.fixture(scope="module")
def X_treino(bruto):
    seg, _ = segmentar(agregar_5min(bruto))
    return montar_X(seg)


def recorte(bruto, agora):
    """Leituras que a API buscaria no banco para este `agora`."""
    return bruto[(bruto["ts"] >= inicio_da_consulta(agora)) & (bruto["ts"] <= agora)]


def test_features_ao_vivo_iguais_ao_treino(bruto, X_treino):
    completas = X_treino[X_treino.notna().all(axis=1)]
    amostra = completas.index[::97]  # ~28 instantes espalhados pelos 10 dias
    assert len(amostra) > 20
    for janela in amostra:
        agora = janela + pd.Timedelta(minutes=7)  # a janela seguinte está em andamento
        X_vivo, motivo = features_ao_vivo(recorte(bruto, agora), agora)
        assert motivo is None, f"{janela}: {motivo}"
        assert X_vivo.index[0] == janela
        esperado = completas.loc[[janela]]
        assert list(X_vivo.columns) == list(esperado.columns)
        np.testing.assert_allclose(X_vivo.to_numpy(float), esperado.to_numpy(float), rtol=1e-9, atol=1e-9)


def test_buraco_vira_dados_insuficientes(bruto):
    # 1º buraco: 04/12 12:00 a 15:00 UTC (09:00 a 12:00 em Recife)
    fim_buraco = pd.Timestamp("2026-12-04 15:00", tz="UTC")

    agora = pd.Timestamp("2026-12-04 12:40", tz="UTC")  # começo do buraco: ainda há dados na janela de 90 min
    X, motivo = features_ao_vivo(recorte(bruto, agora), agora)
    assert X is None and "última leitura há" in motivo

    agora = pd.Timestamp("2026-12-04 13:30", tz="UTC")  # 90 min sem nada
    X, motivo = features_ao_vivo(recorte(bruto, agora), agora)
    assert X is None and "sem leituras" in motivo

    agora = fim_buraco + pd.Timedelta(minutes=35)  # voltou, mas ainda sem 65 min contínuos
    X, motivo = features_ao_vivo(recorte(bruto, agora), agora)
    assert X is None and "dados contínuos" in motivo

    agora = fim_buraco + pd.Timedelta(minutes=67)  # 13 janelas contínuas: já dá
    X, motivo = features_ao_vivo(recorte(bruto, agora), agora)
    assert motivo is None and X.index[0] == fim_buraco + pd.Timedelta(minutes=60)


def test_sem_leituras(bruto):
    agora = pd.Timestamp("2026-12-02 12:00", tz="UTC")
    X, motivo = features_ao_vivo(bruto.iloc[0:0], agora)
    assert X is None and "sem leituras" in motivo


def test_min_janelas_e_65_minutos():
    assert MIN_JANELAS == 13  # janela atual + lags de 5 a 60 min
