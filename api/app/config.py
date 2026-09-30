import os

JWT_SECRET_MIN = 32


def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL não definida")
    return url


def jwt_secret() -> str:
    segredo = os.environ.get("JWT_SECRET", "")
    if len(segredo) < JWT_SECRET_MIN:
        raise RuntimeError(f"JWT_SECRET ausente ou com menos de {JWT_SECRET_MIN} caracteres")
    return segredo


def jwt_expira_min() -> int:
    return int(os.environ.get("JWT_EXPIRA_MIN", "480"))


def cors_origins() -> list[str]:
    """Lista separada por vírgula; vazio = sem CORS."""
    bruto = os.environ.get("CORS_ORIGINS", "")
    return [o.strip() for o in bruto.split(",") if o.strip()]


def validar() -> None:
    """Chamada na subida do app: falha cedo se faltar configuração obrigatória."""
    database_url()
    jwt_secret()
