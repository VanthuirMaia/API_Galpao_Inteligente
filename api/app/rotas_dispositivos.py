from fastapi import APIRouter, Depends, HTTPException, status
from psycopg import sql

from app import config
from app.deps import exigir_admin, get_conn, usuario_atual
from app.modelos import (
    DispositivoBaseOut,
    DispositivoCriadoOut,
    DispositivoIn,
    DispositivoOut,
    DispositivoPatch,
    UltimaOut,
)

router = APIRouter(prefix="/dispositivos", tags=["dispositivos"], dependencies=[Depends(usuario_atual)])

# campos da leitura (sem o payload bruto)
COLUNAS_LEITURA = "ts, ts_origem, recebido_em, t_int, ur_int, t_globo, t_ext, ur_ext, tpo, itgu, rssi"


def exigir_dispositivo(conn, device_id: str) -> None:
    """404 se o dispositivo não existe (ativo ou não)."""
    if conn.execute("SELECT 1 FROM galpao.dispositivos WHERE id = %s", (device_id,)).fetchone() is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "dispositivo não encontrado")


@router.get("", response_model=list[DispositivoOut])
def listar(conn=Depends(get_conn)):
    """Todos os dispositivos. online = recebeu leitura nos últimos ONLINE_LIMITE_S segundos."""
    # LATERAL com ORDER BY ts DESC LIMIT 1 usa o índice (device_id, ts DESC)
    return conn.execute(
        """
        SELECT d.id, d.ambiente, d.descricao, d.ativo,
               u.ts AS ultima_leitura_em,
               COALESCE(u.recebido_em > now() - %s * interval '1 second', false) AS online
        FROM galpao.dispositivos d
        LEFT JOIN LATERAL (
            SELECT ts, recebido_em FROM galpao.leituras l
            WHERE l.device_id = d.id ORDER BY ts DESC LIMIT 1
        ) u ON true
        ORDER BY d.id
        """,
        (config.online_limite_s(),),
    ).fetchall()


@router.get("/{device_id}/ultima", response_model=UltimaOut)
def ultima(device_id: str, conn=Depends(get_conn)):
    exigir_dispositivo(conn, device_id)
    leitura = conn.execute(
        f"SELECT {COLUNAS_LEITURA} FROM galpao.leituras WHERE device_id = %s ORDER BY ts DESC LIMIT 1",
        (device_id,),
    ).fetchone()
    return {"device_id": device_id, "leitura": leitura}


@router.post(
    "",
    response_model=DispositivoCriadoOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(exigir_admin)],
)
def criar(dados: DispositivoIn, conn=Depends(get_conn)):
    """Cadastra o dispositivo. O usuário MQTT correspondente é criado à mão na VPS."""
    dispositivo = conn.execute(
        """
        INSERT INTO galpao.dispositivos (id, ambiente, descricao)
        VALUES (%s, %s, %s)
        ON CONFLICT (id) DO NOTHING
        RETURNING id, ambiente, descricao, ativo, criado_em
        """,
        (dados.id, dados.ambiente, dados.descricao),
    ).fetchone()
    if dispositivo is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "dispositivo já cadastrado")
    aviso = f"cadastre o usuário MQTT na VPS: scripts/criar_usuario_mqtt.sh {dados.id} <senha>"
    return {**dispositivo, "aviso": aviso}


@router.patch("/{device_id}", response_model=DispositivoBaseOut, dependencies=[Depends(exigir_admin)])
def atualizar(device_id: str, dados: DispositivoPatch, conn=Depends(get_conn)):
    """Altera descricao, ambiente e/ou ativo. O id não muda."""
    campos = dados.model_dump(exclude_unset=True)
    # nomes das colunas vêm dos campos do modelo (fixos), não do cliente
    set_sql = sql.SQL(", ").join(sql.SQL("{} = %s").format(sql.Identifier(c)) for c in campos)
    dispositivo = conn.execute(
        sql.SQL(
            "UPDATE galpao.dispositivos SET {} WHERE id = %s RETURNING id, ambiente, descricao, ativo, criado_em"
        ).format(set_sql),
        (*campos.values(), device_id),
    ).fetchone()
    if dispositivo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "dispositivo não encontrado")
    return dispositivo
