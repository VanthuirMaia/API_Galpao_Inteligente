import base64
import json
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.seguranca import criar_token, decodificar_token, hash_senha, verificar_senha


def test_hash_e_verificacao():
    h = hash_senha("senha-correta-123")
    assert h != "senha-correta-123"
    assert verificar_senha("senha-correta-123", h)


def test_senha_errada_falha():
    assert not verificar_senha("outra-senha", hash_senha("senha-correta-123"))


def test_hashes_da_mesma_senha_sao_diferentes():
    assert hash_senha("mesma-senha-123") != hash_senha("mesma-senha-123")


def test_token_ida_e_volta():
    dados = decodificar_token(criar_token(42, "admin"))
    assert dados["sub"] == "42"
    assert dados["perfil"] == "admin"
    assert dados["exp"] > dados["iat"]


def test_token_expirado_rejeitado():
    token = criar_token(1, "leitor", agora=datetime.now(timezone.utc) - timedelta(days=2))
    with pytest.raises(jwt.ExpiredSignatureError):
        decodificar_token(token)


def test_token_adulterado_rejeitado():
    cabecalho, corpo, assinatura = criar_token(1, "leitor").split(".")
    dados = json.loads(base64.urlsafe_b64decode(corpo + "=" * (-len(corpo) % 4)))
    dados["perfil"] = "admin"  # tenta escalar o perfil mantendo a assinatura antiga
    novo = base64.urlsafe_b64encode(json.dumps(dados).encode()).rstrip(b"=").decode()
    with pytest.raises(jwt.InvalidSignatureError):
        decodificar_token(f"{cabecalho}.{novo}.{assinatura}")


def test_token_de_outro_segredo_rejeitado(monkeypatch):
    token = criar_token(1, "admin")
    monkeypatch.setenv("JWT_SECRET", "outro-segredo-tambem-com-mais-de-32-chars")
    with pytest.raises(jwt.InvalidSignatureError):
        decodificar_token(token)


def test_token_malformado_rejeitado():
    with pytest.raises(jwt.PyJWTError):
        decodificar_token("isto.nao.e-um-jwt")
