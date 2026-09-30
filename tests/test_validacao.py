import copy
import json
from datetime import datetime, timedelta, timezone

import pytest

from validacao import validar

AGORA = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
ATIVOS = {"esp01", "esp02"}
TOPICO = "galpao/esp01/leituras"


@pytest.fixture
def payload():
    return {
        "device_id": "esp01",
        "ts": int((AGORA - timedelta(seconds=5)).timestamp()),
        "interno": {"t": 29.5, "ur": 65.2},
        "globo": {"t": 31.0},
        "externo": {"t": 27.1, "ur": 55.0},
        "rssi": -62,
    }


def enviar(p, topico=TOPICO):
    """Serializa o payload (dict) e valida."""
    return validar(topico, json.dumps(p).encode(), ATIVOS, AGORA)


def test_completo(payload):
    leitura, motivo = enviar(payload)
    assert motivo is None
    assert leitura == {
        "device_id": "esp01",
        "ts": datetime.fromtimestamp(payload["ts"], tz=timezone.utc),
        "ts_origem": "esp",
        "t_int": 29.5,
        "ur_int": 65.2,
        "t_globo": 31.0,
        "t_ext": 27.1,
        "ur_ext": 55.0,
        "rssi": -62,
        "payload": payload,
    }


def test_sem_externo(payload):
    del payload["externo"]
    leitura, motivo = enviar(payload)
    assert motivo is None
    assert leitura["t_ext"] is None and leitura["ur_ext"] is None


def test_externo_ur_null(payload):
    payload["externo"]["ur"] = None
    leitura, motivo = enviar(payload)
    assert motivo is None
    assert leitura["t_ext"] == 27.1 and leitura["ur_ext"] is None


def test_globo_ur_ignorada(payload):
    payload["globo"]["ur"] = 50
    leitura, motivo = enviar(payload)
    assert motivo is None
    assert "ur_globo" not in leitura and leitura["t_globo"] == 31.0


def test_temperatura_inteira(payload):
    payload["interno"]["t"] = 28
    leitura, motivo = enviar(payload)
    assert motivo is None and leitura["t_int"] == 28


@pytest.mark.parametrize("rssi", ["ausente", "-62", 50, -121, -62.5, True])
def test_rssi_invalido_vira_none(payload, rssi):
    if rssi == "ausente":
        del payload["rssi"]
    else:
        payload["rssi"] = rssi
    leitura, motivo = enviar(payload)
    assert motivo is None and leitura["rssi"] is None


@pytest.mark.parametrize("ts", ["ausente", None, 0, "1790000000", -5, True,
                                int((AGORA - timedelta(days=2)).timestamp()),
                                int((AGORA + timedelta(days=2)).timestamp())])
def test_ts_invalido_usa_servidor(payload, ts):
    if ts == "ausente":
        del payload["ts"]
    else:
        payload["ts"] = ts
    leitura, motivo = enviar(payload)
    assert motivo is None
    assert leitura["ts"] == AGORA and leitura["ts_origem"] == "servidor"


def test_ts_23h_atras_aceito(payload):
    payload["ts"] = int((AGORA - timedelta(hours=23)).timestamp())
    leitura, motivo = enviar(payload)
    assert motivo is None and leitura["ts_origem"] == "esp"


@pytest.mark.parametrize("topico", ["galpao/esp01", "outro/esp01/leituras",
                                    "galpao//leituras", "galpao/esp01/leituras/x",
                                    "galpao/esp01/status"])
def test_topico_invalido(payload, topico):
    assert enviar(payload, topico) == (None, "topico_invalido")


@pytest.mark.parametrize("dados", [b"\xff\xfe\x00", b'{"device_id": ', b"[1, 2]", b'"texto"'])
def test_json_invalido(dados):
    assert validar(TOPICO, dados, ATIVOS, AGORA) == (None, "json_invalido")


def test_device_id_ausente(payload):
    del payload["device_id"]
    assert enviar(payload) == (None, "device_divergente")


def test_device_id_diferente_do_topico(payload):
    payload["device_id"] = "esp02"
    assert enviar(payload) == (None, "device_divergente")


def test_device_desconhecido(payload):
    payload["device_id"] = "esp99"
    assert enviar(payload, "galpao/esp99/leituras") == (None, "device_desconhecido")


def test_device_inativo(payload):
    assert validar(TOPICO, json.dumps(payload).encode(), {"esp02"}, AGORA) == (None, "device_desconhecido")


def _sem(bloco, chave):
    def f(p):
        del p[bloco][chave]
    return f


def _seta(bloco, chave, valor):
    def f(p):
        p[bloco][chave] = valor
    return f


@pytest.mark.parametrize("alterar, motivo", [
    (_sem("interno", "t"), "campo_ausente:interno.t"),
    (_seta("globo", "t", None), "campo_ausente:globo.t"),
    (_sem("interno", "ur"), "campo_ausente:interno.ur"),
    (lambda p: p.pop("globo"), "campo_ausente:globo.t"),
    (_sem("externo", "t"), "campo_ausente:externo.t"),
    (_seta("interno", "t", True), "valor_invalido:interno.t"),
    (_seta("interno", "t", "28"), "valor_invalido:interno.t"),
    (_seta("externo", "ur", "50"), "valor_invalido:externo.ur"),
    (_seta("interno", "t", 71), "fora_da_faixa:interno.t"),
    (_seta("globo", "t", -11), "fora_da_faixa:globo.t"),
    (_seta("externo", "t", 70.5), "fora_da_faixa:externo.t"),
    (_seta("interno", "ur", 0), "fora_da_faixa:interno.ur"),
    (_seta("interno", "ur", 100.5), "fora_da_faixa:interno.ur"),
    (_seta("externo", "ur", -1), "fora_da_faixa:externo.ur"),
])
def test_rejeitados(payload, alterar, motivo):
    alterar(payload)
    assert enviar(payload) == (None, motivo)


@pytest.mark.parametrize("literal", [b"NaN", b"Infinity", b"-Infinity"])
def test_nao_finitos(literal):
    dados = b'{"device_id": "esp01", "interno": {"t": ' + literal + b', "ur": 60}, "globo": {"t": 30}}'
    assert validar(TOPICO, dados, ATIVOS, AGORA) == (None, "valor_invalido:interno.t")


def test_externo_ur_zero_e_100_aceitos(payload):
    for ur in (0, 100):
        payload["externo"]["ur"] = ur
        assert enviar(payload)[1] is None


def test_payload_original_intacto(payload):
    original = copy.deepcopy(payload)
    leitura, _ = enviar(payload)
    assert leitura["payload"] == original
