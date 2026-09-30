from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app import config
from app.db import criar_pool
from app.rotas_auth import router as rotas_auth


@asynccontextmanager
async def lifespan(app: FastAPI):
    config.validar()  # falha ao iniciar se faltar configuração
    app.state.pool = criar_pool(config.database_url())
    app.state.pool.open()  # não espera o banco: o app sobe mesmo com o banco fora
    yield
    app.state.pool.close()


app = FastAPI(title="Galpão Inteligente - API", lifespan=lifespan)

origens = config.cors_origins()
if origens:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origens,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(rotas_auth)


@app.get("/saude")
def saude(request: Request):
    """Único endpoint sem login."""
    try:
        with request.app.state.pool.connection(timeout=2) as conn:
            conn.execute("SELECT 1")
        banco = True
    except Exception:
        banco = False
    return {"status": "ok", "banco": banco}
