from fastapi import APIRouter, Depends, HTTPException, status
from psycopg import sql

from app import config
from app.classificacao import hoje_recife, situacao
from app.deps import exigir_admin, get_conn, usuario_atual
from app.modelos import (
    DispositivoBaseOut,
    DispositivoCriadoOut,
    DispositivoIn,
    DispositivoOut,
    DispositivoPatch,
    UltimaOut,
)
from app.rotas_faixas import carregar_faixas_ativas

router = APIRouter(prefix="/dispositivos", tags=["dispositivos"], dependencies=[Depends(usuario_atual)])

# campos da leitura (sem o payload bruto)
COLUNAS_LEITURA = "ts, ts_origem, recebido_em, t_int, ur_int, t_globo, t_ext, ur_ext, tpo, itgu, rssi"


def exigir_dispositivo(conn, device_id: str) -> dict:
    """404 se o dispositivo não existe (ativo ou não). Devolve a linha do dispositivo."""
    dispositivo = conn.execute(
        "SELECT id, data_alojamento, faixa_manual_id FROM galpao.dispositivos WHERE id = %s", (device_id,)
    ).fetchone()
    if dispositivo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "dispositivo não encontrado")
    return dispositivo


@router.get("", response_model=list[DispositivoOut])
def listar(conn=Depends(get_conn)):
    """Todos os dispositivos. online = recebeu leitura nos últimos ONLINE_LIMITE_S segundos."""
    # LATERAL com ORDER BY ts DESC LIMIT 1 usa o índice (device_id, ts DESC)
    linhas = conn.execute(
        """
        SELECT d.id, d.ambiente, d.descricao, d.ativo, d.data_alojamento, d.faixa_manual_id,
               u.ts AS ultima_leitura_em, u.itgu AS ultimo_itgu,
               COALESCE(u.recebido_em > now() - %s * interval '1 second', false) AS online
        FROM galpao.dispositivos d
        LEFT JOIN LATERAL (
            SELECT ts, recebido_em, itgu FROM galpao.leituras l
            WHERE l.device_id = d.id ORDER BY ts DESC LIMIT 1
        ) u ON true
        ORDER BY d.id
        """,
        (config.online_limite_s(),),
    ).fetchall()
    # faixas carregadas uma vez, não uma consulta por dispositivo
    faixas, hoje = carregar_faixas_ativas(conn), hoje_recife()
    return [{**d, "situacao": situacao(d, d["ultimo_itgu"], faixas, hoje)} for d in linhas]


@router.get("/{device_id}/ultima", response_model=UltimaOut)
def ultima(device_id: str, conn=Depends(get_conn)):
    dispositivo = exigir_dispositivo(conn, device_id)
    leitura = conn.execute(
        f"SELECT {COLUNAS_LEITURA} FROM galpao.leituras WHERE device_id = %s ORDER BY ts DESC LIMIT 1",
        (device_id,),
    ).fetchone()
    itgu = leitura["itgu"] if leitura else None
    sit = situacao(dispositivo, itgu, carregar_faixas_ativas(conn), hoje_recife())
    return {"device_id": device_id, "leitura": leitura, "situacao": sit}


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
        RETURNING id, ambiente, descricao, ativo, data_alojamento, faixa_manual_id, criado_em
        """,
        (dados.id, dados.ambiente, dados.descricao),
    ).fetchone()
    if dispositivo is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "dispositivo já cadastrado")
    aviso = f"cadastre o usuário MQTT na VPS: scripts/criar_usuario_mqtt.sh {dados.id} <senha>"
    return {**dispositivo, "aviso": aviso}


@router.patch("/{device_id}", response_model=DispositivoBaseOut, dependencies=[Depends(exigir_admin)])
def atualizar(device_id: str, dados: DispositivoPatch, conn=Depends(get_conn)):
    """Altera descricao, ambiente, ativo, data_alojamento e/ou faixa_manual_id. O id não muda."""
    campos = dados.model_dump(exclude_unset=True)
    faixa_id = campos.get("faixa_manual_id")
    if faixa_id is not None:
        existe = conn.execute("SELECT 1 FROM galpao.faixas_itgu WHERE id = %s AND ativo", (faixa_id,)).fetchone()
        if existe is None:
            raise HTTPException(422, "faixa_manual_id inexistente ou inativa")
    # nomes das colunas vêm dos campos do modelo (fixos), não do cliente
    set_sql = sql.SQL(", ").join(sql.SQL("{} = %s").format(sql.Identifier(c)) for c in campos)
    dispositivo = conn.execute(
        sql.SQL(
            "UPDATE galpao.dispositivos SET {} WHERE id = %s "
            "RETURNING id, ambiente, descricao, ativo, data_alojamento, faixa_manual_id, criado_em"
        ).format(set_sql),
        (*campos.values(), device_id),
    ).fetchone()
    if dispositivo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "dispositivo não encontrado")
    return dispositivo
