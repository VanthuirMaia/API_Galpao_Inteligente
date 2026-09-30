import json
import math
from datetime import datetime, timezone

# Códigos de motivo (fixos: serão filtrados por SQL)
TOPICO_INVALIDO = "topico_invalido"
JSON_INVALIDO = "json_invalido"
DEVICE_DIVERGENTE = "device_divergente"
DEVICE_DESCONHECIDO = "device_desconhecido"
CAMPO_AUSENTE = "campo_ausente"    # sufixo ":<campo>"
VALOR_INVALIDO = "valor_invalido"  # sufixo ":<campo>"
FORA_DA_FAIXA = "fora_da_faixa"    # sufixo ":<campo>"

TEMP_MIN, TEMP_MAX = -10, 70
RSSI_MIN, RSSI_MAX = -120, 0
TS_TOLERANCIA_S = 24 * 3600


def _numero(v) -> bool:
    """int ou float finito; bool não conta (é subclasse de int)."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return False
    return math.isfinite(v)


def _faixa_temp(v) -> bool:
    return TEMP_MIN <= v <= TEMP_MAX


def _faixa_ur_int(v) -> bool:
    return 0 < v <= 100


def _faixa_ur_ext(v) -> bool:
    return 0 <= v <= 100


def _obter(dados: dict, bloco: str, chave: str):
    """Lê dados[bloco][chave]; None se o bloco não for objeto ou a chave faltar."""
    sub = dados.get(bloco)
    return sub.get(chave) if isinstance(sub, dict) else None


def _ts(dados: dict, agora: datetime) -> tuple[datetime, str]:
    """ts do ESP se plausível (até 24h de diferença do servidor); senão hora do servidor."""
    ts = dados.get("ts")
    if _numero(ts) and ts > 0 and abs(ts - agora.timestamp()) <= TS_TOLERANCIA_S:
        return datetime.fromtimestamp(ts, tz=timezone.utc), "esp"
    return agora, "servidor"


def _rssi(dados: dict):
    """rssi inválido vira None, sem rejeitar a leitura."""
    r = dados.get("rssi")
    if isinstance(r, int) and not isinstance(r, bool) and RSSI_MIN <= r <= RSSI_MAX:
        return r
    return None


def validar(topico: str, dados: bytes, ativos: set[str], agora: datetime) -> tuple[dict | None, str | None]:
    """Valida uma mensagem. Devolve (leitura, None) ou (None, motivo)."""
    # 1. tópico galpao/{device_id}/leituras
    partes = topico.split("/")
    if len(partes) != 3 or partes[0] != "galpao" or partes[2] != "leituras" or not partes[1]:
        return None, TOPICO_INVALIDO
    device_id = partes[1]

    # 2. UTF-8 + JSON objeto
    try:
        payload = json.loads(dados.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None, JSON_INVALIDO
    if not isinstance(payload, dict):
        return None, JSON_INVALIDO

    # 3 e 4. device_id
    if payload.get("device_id") != device_id:
        return None, DEVICE_DIVERGENTE
    if device_id not in ativos:
        return None, DEVICE_DESCONHECIDO

    # Campos: (nome, valor, obrigatório, validador de faixa)
    campos = [
        ("interno.t", _obter(payload, "interno", "t"), True, _faixa_temp),
        ("interno.ur", _obter(payload, "interno", "ur"), True, _faixa_ur_int),
        ("globo.t", _obter(payload, "globo", "t"), True, _faixa_temp),
    ]
    # 8. bloco externo opcional; se presente, externo.t é obrigatório
    if payload.get("externo") is not None:
        campos.append(("externo.t", _obter(payload, "externo", "t"), True, _faixa_temp))
        campos.append(("externo.ur", _obter(payload, "externo", "ur"), False, _faixa_ur_ext))

    # 5. ausentes (null conta como ausente)
    for nome, v, obrigatorio, _ in campos:
        if obrigatorio and v is None:
            return None, f"{CAMPO_AUSENTE}:{nome}"
    # 6. tipo numérico
    for nome, v, _, _ in campos:
        if v is not None and not _numero(v):
            return None, f"{VALOR_INVALIDO}:{nome}"
    # 7. faixas
    for nome, v, _, faixa in campos:
        if v is not None and not faixa(v):
            return None, f"{FORA_DA_FAIXA}:{nome}"

    ts, ts_origem = _ts(payload, agora)
    return {
        "device_id": device_id,
        "ts": ts,
        "ts_origem": ts_origem,
        "t_int": payload["interno"]["t"],
        "ur_int": payload["interno"]["ur"],
        "t_globo": payload["globo"]["t"],
        "t_ext": _obter(payload, "externo", "t"),
        "ur_ext": _obter(payload, "externo", "ur"),
        "rssi": _rssi(payload),
        "payload": payload,
    }, None
