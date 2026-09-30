from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

from app.deps import get_conn, usuario_atual
from app.seguranca import HASH_FALSO, criar_token, verificar_senha

router = APIRouter(prefix="/auth", tags=["auth"])

CREDENCIAIS_INVALIDAS = "credenciais inválidas"


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    perfil: str
    nome: str


class UsuarioOut(BaseModel):
    id: int
    email: str
    nome: str
    perfil: str


@router.post("/login", response_model=TokenOut)
def login(form: OAuth2PasswordRequestForm = Depends(), conn=Depends(get_conn)):
    email = form.username.strip().lower()
    usuario = conn.execute(
        "SELECT id, nome, perfil, senha_hash, ativo FROM galpao.usuarios WHERE email = %s",
        (email,),
    ).fetchone()

    # verifica sempre (contra hash falso se o email não existe): tempo igual nos dois casos
    senha_ok = verificar_senha(form.password, usuario["senha_hash"] if usuario else HASH_FALSO)
    if usuario is None or not senha_ok or not usuario["ativo"]:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            CREDENCIAIS_INVALIDAS,
            headers={"WWW-Authenticate": "Bearer"},
        )

    conn.execute("UPDATE galpao.usuarios SET ultimo_login = now() WHERE id = %s", (usuario["id"],))
    return TokenOut(
        access_token=criar_token(usuario["id"], usuario["perfil"]),
        perfil=usuario["perfil"],
        nome=usuario["nome"],
    )


@router.get("/me", response_model=UsuarioOut)
def me(usuario: dict = Depends(usuario_atual)):
    return usuario
