-- Galpão Inteligente: faixas de ITGU por idade, alojamento e invalidação de token (idempotente)
-- Rodar como superusuário, depois do 001, 002 e 003.

-- Troca de senha invalida os tokens emitidos antes dela.
-- Usuários existentes recebem now(): precisam logar de novo depois desta migração.
ALTER TABLE galpao.usuarios
    ADD COLUMN IF NOT EXISTS senha_alterada_em timestamptz NOT NULL DEFAULT now();

COMMENT ON COLUMN galpao.usuarios.senha_alterada_em IS
    'Última troca de senha. Tokens com iat (em segundos) anterior a este instante são rejeitados.';

-- Faixas de conforto do ITGU por idade das aves. Nasce vazia: os valores vêm do professor.
CREATE TABLE IF NOT EXISTS galpao.faixas_itgu (
    id                serial PRIMARY KEY,
    nome              text NOT NULL,
    idade_inicio_dias int NOT NULL CHECK (idade_inicio_dias >= 0),
    idade_fim_dias    int NOT NULL,
    critico_min       real NOT NULL,
    conforto_min      real NOT NULL,
    conforto_max      real NOT NULL,
    critico_max       real NOT NULL,
    ativo             boolean NOT NULL DEFAULT true,
    criado_em         timestamptz NOT NULL DEFAULT now(),
    CHECK (idade_fim_dias >= idade_inicio_dias),
    CHECK (critico_min < conforto_min AND conforto_min < conforto_max AND conforto_max < critico_max),
    -- faixas ATIVAS não podem ter idades sobrepostas (range tem gist nativo, sem btree_gist)
    EXCLUDE USING gist (int4range(idade_inicio_dias, idade_fim_dias, '[]') WITH &&) WHERE (ativo)
);

COMMENT ON TABLE galpao.faixas_itgu IS 'Faixas de ITGU por idade (dias de vida). Faixas ativas não se sobrepõem em idade.';
COMMENT ON COLUMN galpao.faixas_itgu.idade_inicio_dias IS 'Idade inicial (dias de vida, inclusiva). O dia do alojamento é a idade 0.';
COMMENT ON COLUMN galpao.faixas_itgu.idade_fim_dias IS 'Idade final (dias de vida, inclusiva).';
COMMENT ON COLUMN galpao.faixas_itgu.conforto_min IS 'ITGU de conforto: conforto_min <= itgu <= conforto_max. Fora disso e dentro dos críticos: alerta.';
COMMENT ON COLUMN galpao.faixas_itgu.critico_min IS 'ITGU abaixo deste valor é crítico (frio).';
COMMENT ON COLUMN galpao.faixas_itgu.critico_max IS 'ITGU acima deste valor é crítico (calor).';

-- Dispositivos: idade do lote e faixa escolhida à mão
ALTER TABLE galpao.dispositivos ADD COLUMN IF NOT EXISTS data_alojamento date;
ALTER TABLE galpao.dispositivos ADD COLUMN IF NOT EXISTS faixa_manual_id int REFERENCES galpao.faixas_itgu (id);

COMMENT ON COLUMN galpao.dispositivos.data_alojamento IS
    'Data de alojamento do lote. A idade em dias é (hoje no fuso de Recife - data); o dia do alojamento é a idade 0.';
COMMENT ON COLUMN galpao.dispositivos.faixa_manual_id IS
    'Faixa escolhida à mão; tem prioridade sobre a faixa calculada pela idade.';

-- API: lê, cria e altera faixas (sem DELETE: desativa-se)
GRANT SELECT, INSERT, UPDATE ON galpao.faixas_itgu TO galpao_api;
GRANT USAGE ON SEQUENCE galpao.faixas_itgu_id_seq TO galpao_api;
