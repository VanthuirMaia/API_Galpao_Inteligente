import psycopg
from fastapi import APIRouter, Depends, HTTPException, status
from psycopg import sql

from app.deps import exigir_admin, get_conn, usuario_atual
from app.modelos import FaixaIn, FaixaOut, FaixaPatch, erro_faixa

router = APIRouter(prefix="/faixas", tags=["faixas"], dependencies=[Depends(usuario_atual)])

COLUNAS = (
    "id, nome, idade_inicio_dias, idade_fim_dias, critico_min, conforto_min, "
    "conforto_max, critico_max, ativo, criado_em"
)
ERRO_SOBREPOSICAO = "a faixa se sobrepõe em idade a outra faixa ativa"


def carregar_faixas_ativas(conn) -> list[dict]:
    """Faixas ativas, por idade. Carregar UMA vez por requisição."""
    return conn.execute(
        f"SELECT {COLUNAS} FROM galpao.faixas_itgu WHERE ativo ORDER BY idade_inicio_dias"
    ).fetchall()


@router.get("", response_model=list[FaixaOut])
def listar(conn=Depends(get_conn)):
    return conn.execute(
        f"SELECT {COLUNAS} FROM galpao.faixas_itgu ORDER BY idade_inicio_dias, id"
    ).fetchall()


@router.post("", response_model=FaixaOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(exigir_admin)])
def criar(dados: FaixaIn, conn=Depends(get_conn)):
    try:
        return conn.execute(
            f"""
            INSERT INTO galpao.faixas_itgu
                (nome, idade_inicio_dias, idade_fim_dias, critico_min, conforto_min, conforto_max, critico_max)
            VALUES (%(nome)s, %(idade_inicio_dias)s, %(idade_fim_dias)s, %(critico_min)s,
                    %(conforto_min)s, %(conforto_max)s, %(critico_max)s)
            RETURNING {COLUNAS}
            """,
            dados.model_dump(),
        ).fetchone()
    except psycopg.errors.ExclusionViolation:
        raise HTTPException(status.HTTP_409_CONFLICT, ERRO_SOBREPOSICAO)


@router.patch("/{faixa_id}", response_model=FaixaOut, dependencies=[Depends(exigir_admin)])
def atualizar(faixa_id: int, dados: FaixaPatch, conn=Depends(get_conn)):
    campos = dados.model_dump(exclude_unset=True)

    atual = conn.execute(f"SELECT {COLUNAS} FROM galpao.faixas_itgu WHERE id = %s", (faixa_id,)).fetchone()
    if atual is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "faixa não encontrada")

    # mesmas validações do POST, sobre os valores finais (atuais + enviados)
    erro = erro_faixa({**atual, **campos})
    if erro:
        raise HTTPException(422, erro)

    if campos.get("ativo") is False and atual["ativo"]:
        em_uso = [
            r["id"]
            for r in conn.execute(
                "SELECT id FROM galpao.dispositivos WHERE faixa_manual_id = %s ORDER BY id", (faixa_id,)
            )
        ]
        if em_uso:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"faixa em uso como faixa manual do(s) dispositivo(s): {', '.join(em_uso)}",
            )

    # nomes das colunas vêm dos campos do modelo (fixos), não do cliente
    set_sql = sql.SQL(", ").join(sql.SQL("{} = %s").format(sql.Identifier(c)) for c in campos)
    try:
        return conn.execute(
            sql.SQL("UPDATE galpao.faixas_itgu SET {} WHERE id = %s RETURNING {}").format(
                set_sql, sql.SQL(COLUNAS)
            ),
            (*campos.values(), faixa_id),
        ).fetchone()
    except psycopg.errors.ExclusionViolation:
        raise HTTPException(status.HTTP_409_CONFLICT, ERRO_SOBREPOSICAO)
