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

    Assim, desativar um usuário (ou trocar a senha dele) corta o acesso na hora.
    """
    try:
        dados = decodificar_token(token)
        usuario_id = int(dados["sub"])
        emitido_em = int(dados["iat"])
    except (jwt.PyJWTError, KeyError, ValueError, TypeError):
        raise _nao_autenticado()

    usuario = conn.execute(
        "SELECT id, email, nome, perfil, ativo, senha_alterada_em FROM galpao.usuarios WHERE id = %s",
        (usuario_id,),
    ).fetchone()
    if usuario is None or not usuario["ativo"]:
        raise _nao_autenticado()
    # Token emitido antes da última troca de senha. O iat é em segundos inteiros: compara com o
    # instante TRUNCADO para segundos, senão um login no mesmo segundo da troca seria rejeitado.
    if emitido_em < int(usuario["senha_alterada_em"].timestamp()):
        raise _nao_autenticado()
    return usuario


def exigir_admin(usuario: dict = Depends(usuario_atual)) -> dict:
    if usuario["perfil"] != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "requer perfil admin")
    return usuario
