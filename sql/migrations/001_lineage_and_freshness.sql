-- Aplicar com psql -X -v ON_ERROR_STOP=1 --single-transaction -f ...
-- Idempotente, sem recriar tabelas ou retroatribuir proveniência histórica.
ALTER TABLE metadata.ingestion_control ADD COLUMN IF NOT EXISTS staging_lineage JSONB;
ALTER TABLE metadata.gold_load_control ADD COLUMN IF NOT EXISTS lineage JSONB NOT NULL DEFAULT '{}'::jsonb;
CREATE OR REPLACE VIEW warehouse.dashboard_freshness AS
SELECT periodo, MAX(finalizado_em) AS ultima_carga
FROM metadata.gold_load_control WHERE status = 'SUCCESS' GROUP BY periodo;
REVOKE ALL ON warehouse.dashboard_freshness FROM PUBLIC;
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='complaints_dashboard') THEN
        GRANT SELECT ON warehouse.dashboard_freshness TO complaints_dashboard;
    END IF;
END $$;
