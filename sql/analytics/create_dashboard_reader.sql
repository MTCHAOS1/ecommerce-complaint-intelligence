-- Executar uma única vez como administrador no banco da aplicação.
-- Sem senha embutida: definir depois com \password complaints_dashboard no psql.
BEGIN;
CREATE ROLE complaints_dashboard LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
    NOINHERIT NOREPLICATION NOBYPASSRLS;
GRANT USAGE ON SCHEMA warehouse TO complaints_dashboard;
GRANT SELECT ON warehouse.fato_reclamacao, warehouse.dim_empresa,
    warehouse.dim_localidade, warehouse.dim_tempo,
    warehouse.dim_classificacao TO complaints_dashboard;
GRANT SELECT ON warehouse.dashboard_freshness TO complaints_dashboard;
ALTER ROLE complaints_dashboard SET default_transaction_read_only = on;
COMMIT;
