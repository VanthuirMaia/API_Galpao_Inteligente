-- Galpão Inteligente: schema inicial (idempotente)

CREATE SCHEMA IF NOT EXISTS galpao;

-- Dispositivos (ESP32). O id é igual ao usuário MQTT.
CREATE TABLE IF NOT EXISTS galpao.dispositivos (
    id         text PRIMARY KEY,
    ambiente   text NOT NULL CHECK (ambiente IN ('modelo', 'real')),
    descricao  text,
    ativo      boolean NOT NULL DEFAULT true,
    criado_em  timestamptz NOT NULL DEFAULT now()
);

-- Leituras já validadas, com ponto de orvalho e ITGU calculados no ingestor
CREATE TABLE IF NOT EXISTS galpao.leituras (
    id          bigserial PRIMARY KEY,
    device_id   text NOT NULL REFERENCES galpao.dispositivos (id),
    ts          timestamptz NOT NULL,
    ts_origem   text NOT NULL CHECK (ts_origem IN ('esp', 'servidor')),
    recebido_em timestamptz NOT NULL DEFAULT now(),
    t_int       real NOT NULL,
    ur_int      real NOT NULL,
    t_globo     real NOT NULL,
    t_ext       real,
    ur_ext      real,
    tpo         real NOT NULL,
    itgu        real NOT NULL,
    rssi        smallint,
    payload     jsonb NOT NULL,
    -- descarta duplicatas do QoS 1
    UNIQUE (device_id, ts)
);

CREATE INDEX IF NOT EXISTS idx_leituras_device_ts
    ON galpao.leituras (device_id, ts DESC);

-- Mensagens rejeitadas pelo ingestor
CREATE TABLE IF NOT EXISTS galpao.erros_ingestao (
    id          bigserial PRIMARY KEY,
    recebido_em timestamptz NOT NULL DEFAULT now(),
    topico      text,
    payload     text,
    motivo      text NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_erros_ingestao_recebido_em
    ON galpao.erros_ingestao (recebido_em DESC);

-- Seed
INSERT INTO galpao.dispositivos (id, ambiente, descricao) VALUES
    ('esp01', 'modelo', 'Galpão-modelo Espaço CRIA'),
    ('esp02', 'real',   'Galpão avícola de validação')
ON CONFLICT DO NOTHING;

-- Comentários
COMMENT ON TABLE galpao.dispositivos IS 'Dispositivos ESP32 cadastrados; o id é o usuário MQTT.';
COMMENT ON TABLE galpao.leituras IS 'Leituras dos sensores com grandezas derivadas calculadas no ingestor.';
COMMENT ON TABLE galpao.erros_ingestao IS 'Mensagens MQTT rejeitadas pelo ingestor, com o motivo.';

COMMENT ON COLUMN galpao.leituras.ts IS 'Momento da medição (UTC).';
COMMENT ON COLUMN galpao.leituras.ts_origem IS 'Origem do ts: esp (relógio do ESP32, NTP válido) ou servidor (ESP sem hora válida; ts = recebido_em).';
COMMENT ON COLUMN galpao.leituras.tpo IS 'Temperatura do ponto de orvalho (°C), calculada no ingestor a partir de t_int e ur_int.';
COMMENT ON COLUMN galpao.leituras.itgu IS 'Índice de Temperatura de Globo e Umidade, calculado no ingestor a partir de t_globo e tpo.';
