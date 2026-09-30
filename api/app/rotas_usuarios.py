from fastapi import APIRouter, Depends, HTTPException, Response, status
from psycopg import sql

from app.deps import exigir_admin, get_conn
from app.modelos import SenhaIn, UsuarioAdminOut, UsuarioCriarIn, UsuarioPatch
from app.seguranca import hash_senha

router = APIRouter(prefix="/usuarios", tags=["usuarios"], dependencies=[Depends(exigir_admin)])

COLUNAS = "id, email, nome, perfil, ativo, criado_em, ultimo_login"  # nunca senha_hash
ERRO_ULTIMO_ADMIN = "o sistema precisa de pelo menos um admin ativo"


@router.get("", response_model=list[UsuarioAdminOut])
def listar(conn=Depends(get_conn)):
    return conn.execute(f"SELECT {COLUNAS} FROM galpao.usuarios ORDER BY id").fetchall()


@router.post("", response_model=UsuarioAdminOut, status_code=status.HTTP_201_CREATED)
def criar(dados: UsuarioCriarIn, conn=Depends(get_conn)):
    usuario = conn.execute(
        f"""
        INSERT INTO galpao.usuarios (email, nome, senha_hash, perfil)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (email) DO NOTHING
        RETURNING {COLUNAS}
        """,
        (dados.email.lower(), dados.nome, hash_senha(dados.senha), dados.perfil),
    ).fetchone()
    if usuario is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "email já cadastrado")
    return usuario


@router.patch("/{usuario_id}", response_model=UsuarioAdminOut)
def atualizar(usuario_id: int, dados: UsuarioPatch, conn=Depends(get_conn)):
    campos = dados.model_dump(exclude_unset=True)

    with conn.transaction():
        # Trava os admins ativos ANTES de checar: dois admins que tentem se rebaixar ao mesmo
        # tempo entram em fila, e o segundo enxerga o estado já alterado pelo primeiro.
        admins = {
            r["id"]
            for r in conn.execute(
                "SELECT id FROM galpao.usuarios WHERE perfil = 'admin' AND ativo ORDER BY id FOR UPDATE"
            )
        }
        alvo = conn.execute(
            f"SELECT {COLUNAS} FROM galpao.usuarios WHERE id = %s FOR UPDATE", (usuario_id,)
        ).fetchone()
        if alvo is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "usuário não encontrado")

        # deixaria de ser admin ativo (rebaixado ou desativado, inclusive o próprio)?
        novo = {**alvo, **campos}
        deixa_de_ser_admin = usuario_id in admins and (novo["perfil"] != "admin" or not novo["ativo"])
        if deixa_de_ser_admin and len(admins) <= 1:
            raise HTTPException(status.HTTP_409_CONFLICT, ERRO_ULTIMO_ADMIN)

        # nomes das colunas vêm dos campos do modelo (fixos), não do cliente
        set_sql = sql.SQL(", ").join(sql.SQL("{} = %s").format(sql.Identifier(c)) for c in campos)
        return conn.execute(
            sql.SQL("UPDATE galpao.usuarios SET {} WHERE id = %s RETURNING {}").format(
                set_sql, sql.SQL(COLUNAS)
            ),
            (*campos.values(), usuario_id),
        ).fetchone()


@router.post("/{usuario_id}/senha", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def definir_senha(usuario_id: int, dados: SenhaIn, conn=Depends(get_conn)):
    """Admin define uma nova senha para o usuário."""
    n = conn.execute(
        "UPDATE galpao.usuarios SET senha_hash = %s, senha_alterada_em = now() WHERE id = %s",
        (hash_senha(dados.senha), usuario_id),
    ).rowcount
    if n == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "usuário não encontrado")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
