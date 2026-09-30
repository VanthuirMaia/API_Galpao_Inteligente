import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer

from app.seguranca import decodificar_token

oauth2 = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_conn(request: Request):
    """Empresta uma conexão do pool durante a requisição."""
    with request.app.state.pool.connection() as conn:
        yield conn


def _nao_autenticado() -> HTTPException:
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        "não autenticado",
        headers={"WWW-Authenticate": "Bearer"},
    )


def usuario_atual(token: str = Depends(oauth2), conn=Depends(get_conn)) -> dict:
    """Usuário do token, buscado no banco a cada requisição.

    Assim, desativar um usuário corta o acesso na hora, sem esperar o token expirar.
    """
    try:
        usuario_id = int(decodificar_token(token)["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise _nao_autenticado()

    usuario = conn.execute(
        "SELECT id, email, nome, perfil, ativo FROM galpao.usuarios WHERE id = %s",
        (usuario_id,),
    ).fetchone()
    if usuario is None or not usuario["ativo"]:
        raise _nao_autenticado()
    return usuario


def exigir_admin(usuario: dict = Depends(usuario_atual)) -> dict:
    if usuario["perfil"] != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "requer perfil admin")
    return usuario
