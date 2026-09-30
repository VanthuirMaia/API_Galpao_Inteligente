import pytest

from itgu import calcular_itgu, itgu_de_leitura, ponto_orvalho

# (t_int, ur_int, t_globo, tpo esperado, itgu esperado)
CASOS = [
    (30, 70, 32, 23.93, 82.11),
    (25, 60, 26, 16.69, 73.51),
    (35, 50, 38, 23.02, 87.79),
]


@pytest.mark.parametrize("t_int, ur_int, t_globo, tpo, itgu", CASOS)
def test_valores_de_referencia(t_int, ur_int, t_globo, tpo, itgu):
    tpo_calc, itgu_calc = itgu_de_leitura(t_int, ur_int, t_globo)
    assert tpo_calc == pytest.approx(tpo, abs=0.01)
    assert itgu_calc == pytest.approx(itgu, abs=0.01)


def test_calcular_itgu_direto():
    assert calcular_itgu(32, 23.93) == pytest.approx(82.11, abs=0.01)


def test_ur_100_tpo_igual_a_t():
    assert ponto_orvalho(28, 100) == pytest.approx(28, abs=0.01)


@pytest.mark.parametrize("ur", [0, 101])
def test_ur_invalida(ur):
    with pytest.raises(ValueError):
        ponto_orvalho(25, ur)


@pytest.mark.parametrize("ur", [1, 10, 35, 60, 99, 100])
@pytest.mark.parametrize("t", [15, 25, 35])
def test_tpo_nao_excede_t(t, ur):
    assert ponto_orvalho(t, ur) <= t + 1e-9
