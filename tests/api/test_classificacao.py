from datetime import date, timedelta

import pytest

from app.classificacao import classificar, escolher_faixa, hoje_recife, idade_em_dias, situacao

HOJE = date(2026, 10, 10)


def faixa(id_, inicio, fim, cmin=65.0, min_=70.0, max_=77.0, cmax=82.0, nome=None):
    return {
        "id": id_, "nome": nome or f"Faixa {id_}", "idade_inicio_dias": inicio, "idade_fim_dias": fim,
        "critico_min": cmin, "conforto_min": min_, "conforto_max": max_, "critico_max": cmax,
    }


F1, F2, F3 = faixa(1, 0, 7), faixa(2, 8, 14), faixa(3, 15, 21)
FAIXAS = [F1, F2, F3]


def disp(alojamento=None, manual=None):
    return {"data_alojamento": alojamento, "faixa_manual_id": manual}


# ---------- idade ----------

def test_idade_mesmo_dia_e_zero():
    assert idade_em_dias(HOJE, HOJE) == 0


def test_idade_sete_dias_depois():
    assert idade_em_dias(HOJE - timedelta(days=7), HOJE) == 7


def test_hoje_recife_usa_o_fuso_local():
    from datetime import datetime, timezone
    # 01:00 UTC do dia 11 ainda é dia 10 em Recife (UTC-3)
    assert hoje_recife(datetime(2026, 10, 11, 1, 0, tzinfo=timezone.utc)) == date(2026, 10, 10)
    assert hoje_recife(datetime(2026, 10, 11, 3, 0, tzinfo=timezone.utc)) == date(2026, 10, 11)


# ---------- escolher_faixa ----------

def test_manual_tem_prioridade_sobre_a_idade():
    alojado = HOJE - timedelta(days=10)  # idade 10 -> F2 pela idade
    f, origem, idade = escolher_faixa(disp(alojado, manual=3), FAIXAS, HOJE)
    assert (f, origem, idade) == (F3, "manual", 10)


def test_manual_sem_data_de_alojamento():
    assert escolher_faixa(disp(None, manual=1), FAIXAS, HOJE) == (F1, "manual", None)


@pytest.mark.parametrize("idade, esperada", [
    (5, F1),    # dentro
    (0, F1),    # borda de início (dia do alojamento)
    (7, F1),    # borda de fim
    (8, F2),    # borda de início da seguinte
    (14, F2),
    (15, F3),
    (21, F3),   # última borda
])
def test_faixa_pela_idade(idade, esperada):
    f, origem, dias = escolher_faixa(disp(HOJE - timedelta(days=idade)), FAIXAS, HOJE)
    assert (f, origem, dias) == (esperada, "idade", idade)


def test_idade_sem_faixa_cobrindo():
    f, origem, idade = escolher_faixa(disp(HOJE - timedelta(days=30)), FAIXAS, HOJE)
    assert (f, origem, idade) == (None, None, 30)


def test_idade_em_buraco_entre_faixas():
    faixas = [faixa(1, 0, 7), faixa(2, 10, 14)]  # dias 8 e 9 sem faixa
    assert escolher_faixa(disp(HOJE - timedelta(days=8)), faixas, HOJE)[0] is None


def test_sem_data_e_sem_manual():
    assert escolher_faixa(disp(), FAIXAS, HOJE) == (None, None, None)


def test_sem_faixas_ativas():
    assert escolher_faixa(disp(HOJE - timedelta(days=3)), [], HOJE) == (None, None, 3)


def test_manual_que_nao_esta_entre_as_ativas_cai_para_a_idade():
    f, origem, _ = escolher_faixa(disp(HOJE - timedelta(days=10), manual=99), FAIXAS, HOJE)
    assert (f, origem) == (F2, "idade")


# ---------- classificar (conforto 70–77, crítico < 65 ou > 82) ----------

@pytest.mark.parametrize("itgu, esperado", [
    (73.0, "conforto"),
    (70.0, "conforto"),   # borda exata inferior
    (77.0, "conforto"),   # borda exata superior
    (69.9, "alerta"),
    (65.0, "alerta"),     # borda exata do crítico: ainda alerta
    (77.1, "alerta"),
    (82.0, "alerta"),     # borda exata do crítico: ainda alerta
    (64.9, "critico"),
    (82.1, "critico"),
])
def test_classificar(itgu, esperado):
    assert classificar(itgu, F1) == esperado


def test_classificar_sem_faixa():
    assert classificar(75.0, None) == "sem_faixa"


# ---------- situacao (bloco da API) ----------

def test_situacao_completa():
    s = situacao(disp(HOJE - timedelta(days=10)), 75.0, FAIXAS, HOJE)
    assert s == {"idade_dias": 10, "origem_faixa": "idade", "faixa": F2, "classificacao": "conforto"}


def test_situacao_sem_leitura_tem_classificacao_nula():
    s = situacao(disp(HOJE - timedelta(days=10)), None, FAIXAS, HOJE)
    assert s["classificacao"] is None and s["faixa"] == F2


def test_situacao_sem_faixa():
    s = situacao(disp(), 75.0, FAIXAS, HOJE)
    assert s == {"idade_dias": None, "origem_faixa": None, "faixa": None, "classificacao": "sem_faixa"}
