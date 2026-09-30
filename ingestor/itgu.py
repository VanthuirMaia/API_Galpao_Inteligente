import math

# Constantes de Sonntag para a fórmula de Magnus
MAGNUS_A = 17.62
MAGNUS_B = 243.12


def ponto_orvalho(t: float, ur: float) -> float:
    """Ponto de orvalho (°C) pela fórmula de Magnus (constantes de Sonntag).

    t em °C, ur em % (0 < ur <= 100).
    """
    if ur <= 0 or ur > 100:
        raise ValueError(f"ur fora do intervalo (0, 100]: {ur}")
    g = math.log(ur / 100) + (MAGNUS_A * t) / (MAGNUS_B + t)
    return MAGNUS_B * g / (MAGNUS_A - g)


def calcular_itgu(t_globo: float, tpo: float) -> float:
    """ITGU = t_globo + 0.36 * tpo + 41.5 (Buffington et al., 1981). Temperaturas em °C."""
    return t_globo + 0.36 * tpo + 41.5


def itgu_de_leitura(t_int: float, ur_int: float, t_globo: float) -> tuple[float, float]:
    """Devolve (tpo, itgu) de uma leitura. Sem arredondamento."""
    tpo = ponto_orvalho(t_int, ur_int)
    return tpo, calcular_itgu(t_globo, tpo)
