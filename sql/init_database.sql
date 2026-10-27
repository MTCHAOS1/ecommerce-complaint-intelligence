-- Inicialização exclusiva de banco novo. Executar com psql -X -v ON_ERROR_STOP=1.
-- Todos os scripts abaixo participam da mesma transação.
\set ON_ERROR_STOP on
BEGIN;

DO $$
BEGIN
    IF current_setting('server_version_num')::INTEGER < 150000 THEN
        RAISE EXCEPTION 'A inicialização requer PostgreSQL 15 ou superior.';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_class AS relation
        JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
        WHERE namespace.nspname IN ('staging', 'warehouse', 'metadata')
    ) THEN
        RAISE EXCEPTION
            'Inicialização recusada: staging, warehouse ou metadata já contém objetos. Use um banco novo; este script não executa migrações.';
    END IF;
END $$;

\ir setup_schemas.sql
\ir staging/create_complaints.sql
\ir staging/create_ingestion_control.sql
\ir staging/update_ingestion_control.sql
\ir warehouse/create_star_schema.sql
\ir warehouse/create_gold_load_control.sql

COMMIT;
