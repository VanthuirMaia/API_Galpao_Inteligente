from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


def criar_pool(url: str) -> ConnectionPool:
    """Pool (1 a 5 conexões), ainda fechado; o lifespan do app abre e fecha.

    timeout curto: com o banco fora, a requisição falha rápido em vez de ficar pendurada.
    """
    return ConnectionPool(
        url,
        min_size=1,
        max_size=5,
        timeout=5,
        open=False,
        kwargs={"autocommit": True, "row_factory": dict_row},
    )
