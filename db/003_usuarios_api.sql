-- Galpão Inteligente: usuários da API e role galpao_api (idempotente)
-- Rodar como superusuário, depois do 001 e do 002.
-- SEM senhas aqui: defina na VPS com  ALTER ROLE galpao_api PASSWORD '...';

CREATE TABLE IF NOT EXISTS galpao.usuarios (
    id           serial PRIMARY KEY,
    email        text NOT NULL UNIQUE CHECK (email = lower(email)),
    nome         text NOT NULL,
    senha_hash   text NOT NULL,
    perfil       text NOT NULL CHECK (perfil IN ('admin', 'leitor')),
    ativo        boolean NOT NULL DEFAULT true,
    criado_em    timestamptz NOT NULL DEFAULT now(),
    ultimo_login timestamptz
);

COMMENT ON TABLE galpao.usuarios IS 'Usuários do painel/API. Desativa-se (ativo = false), não se apaga.';
COMMENT ON COLUMN galpao.usuarios.senha_hash IS 'Hash Argon2 da senha; nunca a senha em texto.';
COMMENT ON COLUMN galpao.usuarios.perfil IS 'admin (configura) ou leitor (só consulta).';

-- Role da API (criada só se não existir). Não é dona de nenhum objeto.
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'galpao_api') THEN
        CREATE ROLE galpao_api LOGIN;
    END IF;
END
$$;

GRANT USAGE ON SCHEMA galpao TO galpao_api;
GRANT SELECT ON galpao.leituras, galpao.erros_ingestao, galpao.dispositivos, galpao.usuarios TO galpao_api;
-- sem DELETE: dispositivos e usuários são desativados, não apagados
GRANT INSERT, UPDATE ON galpao.dispositivos, galpao.usuarios TO galpao_api;
GRANT USAGE ON SEQUENCE galpao.usuarios_id_seq TO galpao_api;

-- Remove a galpao_leitura (criada na 002, nunca usada): o ALTER DEFAULT PRIVILEGES
-- da 002 daria a ela SELECT automático em usuarios, ou seja, acesso aos hashes de senha.
DO $$
BEGIN
    IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'galpao_leitura') THEN
        ALTER DEFAULT PRIVILEGES IN SCHEMA galpao REVOKE SELECT ON TABLES FROM galpao_leitura;
        REVOKE ALL ON ALL TABLES IN SCHEMA galpao FROM galpao_leitura;
        REVOKE USAGE ON SCHEMA galpao FROM galpao_leitura;
        DROP ROLE galpao_leitura;
    END IF;
END
$$;
