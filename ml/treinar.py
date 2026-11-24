"""Divisão temporal e treino: persistência, regressão linear e XGBoost."""
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBRegressor

from features import HORIZONTE_MIN

FRACAO_TESTE = 0.2


def dividir_temporal(X, y):
    """Últimos 20% das linhas (em ordem de tempo) viram teste, sem embaralhar.

    O alvo olha 30 min à frente, então o treino termina 30 min antes do
    início do teste, para nenhum alvo de treino invadir o período de teste.
    """
    corte = X.index[int(len(X) * (1 - FRACAO_TESTE))]
    treino = X.index <= corte - pd.Timedelta(minutes=HORIZONTE_MIN)
    teste = X.index >= corte
    return X[treino], X[teste], y[treino], y[teste]


def calcular_metricas(real, previsto):
    """MAE e RMSE em unidades de ITGU."""
    erro = np.asarray(real) - np.asarray(previsto)
    return {"mae": float(np.abs(erro).mean()), "rmse": float(np.sqrt((erro**2).mean()))}


def treinar(X, y):
    """Treina e avalia os três modelos. Devolve (resultado, modelo_xgb)."""
    X_tr, X_te, y_tr, y_te = dividir_temporal(X, y)

    linear = make_pipeline(StandardScaler(), LinearRegression()).fit(X_tr, y_tr)
    xgb = XGBRegressor(n_estimators=300, max_depth=4, learning_rate=0.05,
                       subsample=0.8, colsample_bytree=0.8, random_state=42).fit(X_tr, y_tr)

    previsoes = pd.DataFrame({
        "real": y_te,
        "persistencia": X_te["itgu"],  # ITGU atual como previsão de daqui a 30 min
        "linear": linear.predict(X_te),
        "xgboost": xgb.predict(X_te),
    }, index=X_te.index)

    metricas = {m: calcular_metricas(previsoes["real"], previsoes[m])
                for m in ("persistencia", "linear", "xgboost")}
    resultado = {
        "metricas": metricas,
        "previsoes": previsoes,
        "n_treino": len(X_tr), "n_teste": len(X_te),
        "treino_inicio": X_tr.index[0], "treino_fim": X_tr.index[-1],
        "teste_inicio": X_te.index[0], "teste_fim": X_te.index[-1],
        "importancias": pd.Series(xgb.feature_importances_, index=X.columns).sort_values(),
    }
    return resultado
