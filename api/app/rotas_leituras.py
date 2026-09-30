import csv
import io
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import AwareDatetime

from app.deps import get_conn, usuario_atual
from app.modelos import LeiturasOut
from app.rotas_dispositivos import COLUNAS_LEITURA, exigir_dispositivo

router = APIRouter(prefix="/leituras", tags=["leituras"], dependencies=[Depends(usuario_atual)])

JANELA_PADRAO = timedelta(hours=24)
INTERVALO_MAX = timedelta(days=31)
SEGUNDOS = {"5min": 300, "15min": 900, "1h": 3600}
LOTE_CSV = 1000

Agregacao = Literal["bruto", "5min", "15min", "1h"]

COLUNAS_BRUTO = [c.strip() for c in COLUNAS_LEITURA.split(",")]
COLUNAS_AGREGADO = [
    "janela", "n", "t_int", "ur_int", "t_globo", "t_ext", "ur_ext", "tpo", "itgu", "itgu_min", "itgu_max",
]

SQL_BRUTO = f"""
    SELECT {COLUNAS_LEITURA} FROM galpao.leituras
    WHERE device_id = %(device_id)s AND ts >= %(inicio)s AND ts <= %(fim)s
    ORDER BY ts
"""
# as N leituras mais recentes do período, devolvidas em ordem crescente
SQL_BRUTO_LIMITE = f"""
    SELECT * FROM (
        SELECT {COLUNAS_LEITURA} FROM galpao.leituras
        WHERE device_id = %(device_id)s AND ts >= %(inicio)s AND ts <= %(fim)s
        ORDER BY ts DESC LIMIT %(limite)s
    ) recentes ORDER BY ts
"""
# janela por floor(epoch / N) * N: funciona em qualquer versão do Postgres (sem date_bin)
SQL_AGREGADO = """
    SELECT to_timestamp(floor(extract(epoch FROM ts) / %(seg)s) * %(seg)s) AS janela,
           count(*) AS n,
           round(avg(t_int)::numeric, 2)::float8 AS t_int,
           round(avg(ur_int)::numeric, 2)::float8 AS ur_int,
           round(avg(t_globo)::numeric, 2)::float8 AS t_globo,
           round(avg(t_ext)::numeric, 2)::float8 AS t_ext,
           round(avg(ur_ext)::numeric, 2)::float8 AS ur_ext,
           round(avg(tpo)::numeric, 2)::float8 AS tpo,
           round(avg(itgu)::numeric, 2)::float8 AS itgu,
           round(min(itgu)::numeric, 2)::float8 AS itgu_min,
           round(max(itgu)::numeric, 2)::float8 AS itgu_max
    FROM galpao.leituras
    WHERE device_id = %(device_id)s AND ts >= %(inicio)s AND ts <= %(fim)s
    GROUP BY 1 ORDER BY 1
"""


def resolver_periodo(inicio: datetime | None, fim: datetime | None) -> tuple[datetime, datetime]:
    """Aplica o padrão (últimas 24 h) e valida o período. Devolve os dois em UTC."""
    fim = fim or datetime.now(timezone.utc)
    inicio = inicio or fim - JANELA_PADRAO
    inicio, fim = inicio.astimezone(timezone.utc), fim.astimezone(timezone.utc)
    if fim <= inicio:
        raise HTTPException(422, "fim deve ser maior que inicio")
    if fim - inicio > INTERVALO_MAX:
        raise HTTPException(422, "intervalo máximo de 31 dias")
    return inicio, fim


def parametros_consulta(
    device_id: str = Query(..., description="id do dispositivo, ex.: esp01"),
    inicio: AwareDatetime | None = Query(None, description="ISO 8601 com fuso; padrão: fim - 24 h"),
    fim: AwareDatetime | None = Query(None, description="ISO 8601 com fuso; padrão: agora"),
    agregacao: Agregacao = Query("bruto"),
    conn=Depends(get_conn),
) -> dict:
    """Parâmetros e validações comuns a /leituras e /leituras/csv."""
    inicio, fim = resolver_periodo(inicio, fim)
    exigir_dispositivo(conn, device_id)
    return {"device_id": device_id, "inicio": inicio, "fim": fim, "agregacao": agregacao}


def montar_consulta(p: dict, limite: int | None = None) -> tuple[str, dict, list[str]]:
    """(sql, parâmetros, colunas) para o período e a agregação pedidos."""
    params = {"device_id": p["device_id"], "inicio": p["inicio"], "fim": p["fim"]}
    if p["agregacao"] != "bruto":
        params["seg"] = SEGUNDOS[p["agregacao"]]
        return SQL_AGREGADO, params, COLUNAS_AGREGADO
    if limite is not None:
        params["limite"] = limite
        return SQL_BRUTO_LIMITE, params, COLUNAS_BRUTO
    return SQL_BRUTO, params, COLUNAS_BRUTO


@router.get("", response_model=LeiturasOut)
def listar(
    p: dict = Depends(parametros_consulta),
    limite: int = Query(5000, ge=1, le=20000, description="só para agregacao=bruto; vale as mais recentes"),
    conn=Depends(get_conn),
):
    """Período [inicio, fim] em ordem crescente de ts."""
    sql, params, _ = montar_consulta(p, limite if p["agregacao"] == "bruto" else None)
    itens = conn.execute(sql, params).fetchall()
    return {**p, "total": len(itens), "itens": itens}


def _valor_csv(v) -> str:
    """ts em ISO UTC (o pandas lê direto); None vira campo vazio."""
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.astimezone(timezone.utc).isoformat()
    return str(v)


def _gerar_csv(pool, sql: str, params: dict, colunas: list[str]):
    """Gera o CSV em streaming: cursor nomeado no servidor + fetchmany, sem carregar tudo."""
    saida = io.StringIO()
    escritor = csv.writer(saida, lineterminator="\n")

    def pegar() -> str:
        texto = saida.getvalue()
        saida.seek(0)
        saida.truncate(0)
        return texto

    escritor.writerow(colunas)
    yield pegar()
    # conexão própria: a da requisição pode ser devolvida ao pool antes do fim do streaming
    with pool.connection() as conn, conn.transaction(), conn.cursor(name="csv_leituras") as cur:
        cur.execute(sql, params)
        while lote := cur.fetchmany(LOTE_CSV):
            for linha in lote:
                escritor.writerow([_valor_csv(linha[c]) for c in colunas])
            yield pegar()


@router.get("/csv", response_class=StreamingResponse)
def exportar_csv(request: Request, p: dict = Depends(parametros_consulta)):
    """Mesmos parâmetros do /leituras (sem limite de linhas), em CSV."""
    sql, params, colunas = montar_consulta(p)
    nome = f"galpao_{p['device_id']}_{p['inicio']:%Y%m%d}_{p['fim']:%Y%m%d}.csv"
    return StreamingResponse(
        _gerar_csv(request.app.state.pool, sql, params, colunas),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )
