from fastapi import APIRouter, Depends, Query

from app.deps import get_conn, usuario_atual
from app.modelos import ErroOut

router = APIRouter(prefix="/erros", tags=["erros"], dependencies=[Depends(usuario_atual)])


@router.get("", response_model=list[ErroOut])
def listar(
    device_id: str | None = Query(None, description="filtra pelo tópico galpao/<id>/leituras"),
    limite: int = Query(50, ge=1, le=500),
    conn=Depends(get_conn),
):
    """Últimas mensagens rejeitadas pelo ingestor, mais recentes primeiro."""
    topico = f"galpao/{device_id}/leituras" if device_id else None
    return conn.execute(
        """
        SELECT recebido_em, topico, motivo, left(payload, 500) AS payload
        FROM galpao.erros_ingestao
        WHERE (%(topico)s::text IS NULL OR topico = %(topico)s)
        ORDER BY recebido_em DESC, id DESC
        LIMIT %(limite)s
        """,
        {"topico": topico, "limite": limite},
    ).fetchall()
