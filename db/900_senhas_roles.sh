#!/bin/bash
# Define as senhas das roles galpao_ingestor e galpao_api na primeira inicialização do Postgres.
# O entrypoint da imagem executa este arquivo com "source" (sem bit de execução), por isso
# NÃO usar "exit" nem "set -e" aqui. As senhas vão como variáveis do psql (-v / :'var'),
# nunca interpoladas no texto do SQL.
if [ -z "$PG_SENHA_INGESTOR" ] || [ -z "$PG_SENHA_API" ]; then
    echo "AVISO: PG_SENHA_INGESTOR e/ou PG_SENHA_API vazias; senhas das roles NÃO definidas (ok em dev)."
else
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
        -v senha_ingestor="$PG_SENHA_INGESTOR" -v senha_api="$PG_SENHA_API" <<'SQL'
ALTER ROLE galpao_ingestor PASSWORD :'senha_ingestor';
ALTER ROLE galpao_api PASSWORD :'senha_api';
SQL
    echo "senhas de galpao_ingestor e galpao_api definidas"
fi
