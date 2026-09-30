from datetime import datetime, timedelta, timezone

import jwt
from pwdlib import PasswordHash

from app import config

ALGORITMO = "HS256"

# Argon2 (recomendação do pwdlib / tutorial oficial do FastAPI)
_hasher = PasswordHash.recommended()


def hash_senha(senha: str) -> str:
    return _hasher.hash(senha)


def verificar_senha(senha: str, hash_: str) -> bool:
    return _hasher.verify(senha, hash_)


# Hash fixo para gastar o mesmo tempo quando o email não existe (evita revelar quais emails existem)
HASH_FALSO = hash_senha("senha-descartavel-so-para-igualar-o-tempo")


def criar_token(usuario_id: int, perfil: str, agora: datetime | None = None) -> str:
    """JWT HS256 com sub (id como string), perfil, iat e exp."""
    agora = agora or datetime.now(timezone.utc)
    payload = {
        "sub": str(usuario_id),
        "perfil": perfil,
        "iat": agora,
        "exp": agora + timedelta(minutes=config.jwt_expira_min()),
    }
    return jwt.encode(payload, config.jwt_secret(), algorithm=ALGORITMO)


def decodificar_token(token: str) -> dict:
    """Devolve o payload. Levanta jwt.PyJWTError se expirado, adulterado ou malformado."""
    return jwt.decode(
        token,
        config.jwt_secret(),
        algorithms=[ALGORITMO],
        options={"require": ["exp", "sub", "iat"]},
        leeway=10,  # tolera pequena diferença de relógio (iat "no futuro") entre API e banco
    )
