-- Uso administrativo: psql -X -v ON_ERROR_STOP=1 -v expected_period=YYYY-MM -f ...
-- Prefira python -m src.database.load_gold YYYY-MM para registrar auditoria.
\set ON_ERROR_STOP on
BEGIN;
DO $$
BEGIN
    IF NOT pg_try_advisory_xact_lock(20261020::bigint) THEN
        RAISE EXCEPTION 'Outra operação Gold está em andamento.';
    END IF;
END $$;
SELECT set_config('app.expected_period', :'expected_period', true);
\ir load_star_schema_body.sql
COMMIT;
