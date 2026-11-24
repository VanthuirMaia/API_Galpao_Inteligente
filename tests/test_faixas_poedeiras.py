"""Faixas de ITGU de poedeiras (scripts/aplicar_faixas_poedeiras.py): classificação nos limites.

Sem banco: usa a mesma lista FAIXAS do script, a mesma escolha por idade e a mesma classificação da API.
"""
from datetime import date, timedelta

import pytest

from aplicar_faixas_poedeiras import FAIXAS
from app.classificacao import classificar, escolher_faixa

CAMPOS = ("nome", "idade_inicio_dias", "idade_fim_dias", "critico_min", "conforto_min", "conforto_max", "critico_max")
FAIXAS_ATIVAS = [{"id": i, **dict(zip(CAMPOS, f))} for i, f in enumerate(FAIXAS, start=1)]
HOJE = date(2026, 6, 15)


def classe(idade_dias: int, itgu: float) -> str:
    """Classificação de um ITGU para um lote com essa idade (dias desde o alojamento)."""
    dispositivo = {"data_alojamento": HOJE - timedelta(days=idade_dias), "faixa_manual_id": None}
    faixa, _, _ = escolher_faixa(dispositivo, FAIXAS_ATIVAS, HOJE)
    return classificar(itgu, faixa)


@pytest.mark.parametrize("itgu, esperado", [
    (74.9, "conforto"),
    (75.0, "conforto"),   # "conforto até 75,0": o limite ainda é conforto
    (76.0, "alerta"),
    (78.0, "alerta"),     # "crítico acima de 78,0": o limite ainda é alerta
    (78.1, "critico"),
    (50.0, "conforto"),   # não há limite inferior na literatura
])
def test_adultas_recria_e_producao(itgu, esperado):
    assert classe(100, itgu) == esperado


@pytest.mark.parametrize("idade, itgu, esperado", [
    (3, 83.0, "conforto"), (3, 89.0, "conforto"), (3, 82.9, "alerta"), (3, 89.1, "alerta"),
    (3, 120.0, "alerta"), (3, 10.0, "alerta"),    # fora do conforto é alerta; nunca crítico
    (10, 77.0, "conforto"), (10, 81.0, "conforto"), (10, 76.9, "alerta"), (10, 81.1, "alerta"),
    (10, 120.0, "alerta"), (10, 10.0, "alerta"),
])
def test_cria_primeira_e_segunda_semana(idade, itgu, esperado):
    assert classe(idade, itgu) == esperado


@pytest.mark.parametrize("idade", [15, 20, 42])
def test_sem_faixa_de_15_a_42_dias(idade):
    assert classe(idade, 80.0) == "sem_faixa"


@pytest.mark.parametrize("idade, nome_da_faixa", [
    (0, "Cria 1ª semana"), (7, "Cria 1ª semana"), (8, "Cria 2ª semana"), (14, "Cria 2ª semana"),
    (43, "Recria e produção"), (1000, "Recria e produção"),
])
def test_idades_nas_pontas_das_faixas(idade, nome_da_faixa):
    dispositivo = {"data_alojamento": HOJE - timedelta(days=idade), "faixa_manual_id": None}
    faixa, origem, _ = escolher_faixa(dispositivo, FAIXAS_ATIVAS, HOJE)
    assert origem == "idade" and nome_da_faixa in faixa["nome"]


def test_acima_de_1000_dias_sem_faixa():
    assert classe(1001, 70.0) == "sem_faixa"


def test_lista_do_script_nao_se_sobrepoe():
    intervalos = sorted((f[1], f[2]) for f in FAIXAS)
    assert all(fim < proximo_inicio for (_, fim), (proximo_inicio, _) in zip(intervalos, intervalos[1:]))
