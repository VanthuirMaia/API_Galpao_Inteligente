-- Galpão Inteligente: roles e permissões (idempotente)
-- Rodar como superusuário, depois do 001_init.sql.
-- SEM senhas aqui: defina na VPS com  ALTER ROLE <role> PASSWORD '...';

-- Roles de aplicação (criadas só se não existirem). Não são donas de nenhum objeto.
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'galpao_ingestor') THEN
        CREATE ROLE galpao_ingestor LOGIN;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'galpao_leitura') THEN
        CREATE ROLE galpao_leitura LOGIN;
    END IF;
END
$$;

-- Ingestor: lê dispositivos, grava leituras e erros
GRANT USAGE ON SCHEMA galpao TO galpao_ingestor;
GRANT SELECT ON galpao.dispositivos TO galpao_ingestor;
-- o SELECT em leituras é exigido pelo INSERT ... ON CONFLICT ... RETURNING id
GRANT SELECT, INSERT ON galpao.leituras TO galpao_ingestor;
GRANT INSERT ON galpao.erros_ingestao TO galpao_ingestor;
GRANT USAGE ON SEQUENCE galpao.leituras_id_seq, galpao.erros_ingestao_id_seq TO galpao_ingestor;

-- API (parte 2): somente leitura
GRANT USAGE ON SCHEMA galpao TO galpao_leitura;
GRANT SELECT ON ALL TABLES IN SCHEMA galpao TO galpao_leitura;
-- tabelas futuras criadas pelo role que executa este script
ALTER DEFAULT PRIVILEGES IN SCHEMA galpao GRANT SELECT ON TABLES TO galpao_leitura;
