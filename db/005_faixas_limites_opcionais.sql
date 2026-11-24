-- Galpão Inteligente: limites de ITGU opcionais nas faixas (idempotente)
-- Rodar como superusuário, depois do 004.
--
-- Na literatura nem toda fase tem os quatro limites (ex.: poedeiras adultas têm só "conforto até 75,
-- alerta de 75 a 78, crítico acima de 78"). Limite nulo = não existe: nunca é conforto-mínimo/crítico por ali.
-- O limite superior de conforto (conforto_max) continua obrigatório.

ALTER TABLE galpao.faixas_itgu ALTER COLUMN critico_min DROP NOT NULL;
ALTER TABLE galpao.faixas_itgu ALTER COLUMN conforto_min DROP NOT NULL;
ALTER TABLE galpao.faixas_itgu ALTER COLUMN critico_max DROP NOT NULL;

-- troca a CHECK de ordem (a da 004 não tem nome fixo) por uma que ignora os limites nulos
DO $$
DECLARE r record;
BEGIN
    FOR r IN
        SELECT conname FROM pg_constraint
        WHERE conrelid = 'galpao.faixas_itgu'::regclass AND contype = 'c'
          AND conname <> 'faixas_itgu_limites_ordenados'
          AND pg_get_constraintdef(oid) LIKE '%critico_min < conforto_min%'
    LOOP
        EXECUTE format('ALTER TABLE galpao.faixas_itgu DROP CONSTRAINT %I', r.conname);
    END LOOP;
END $$;

ALTER TABLE galpao.faixas_itgu DROP CONSTRAINT IF EXISTS faixas_itgu_limites_ordenados;
ALTER TABLE galpao.faixas_itgu ADD CONSTRAINT faixas_itgu_limites_ordenados CHECK (
    (conforto_min IS NULL OR conforto_min < conforto_max)
    AND (critico_max IS NULL OR conforto_max < critico_max)
    -- crítico inferior só existe se há conforto inferior
    AND (critico_min IS NULL OR (conforto_min IS NOT NULL AND critico_min < conforto_min))
);

COMMENT ON COLUMN galpao.faixas_itgu.conforto_min IS 'ITGU de conforto: conforto_min <= itgu <= conforto_max (nulo = sem limite inferior). Fora disso e dentro dos críticos: alerta.';
COMMENT ON COLUMN galpao.faixas_itgu.critico_min IS 'ITGU abaixo deste valor é crítico (frio). Nulo = não há limite crítico inferior.';
COMMENT ON COLUMN galpao.faixas_itgu.critico_max IS 'ITGU acima deste valor é crítico (calor). Nulo = não há limite crítico superior.';
