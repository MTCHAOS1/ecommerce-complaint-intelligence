-- Executar uma unica vez no banco existente, sem recriar as tabelas.
BEGIN;
ALTER TABLE warehouse.dim_empresa DROP CONSTRAINT uq_dim_empresa;
ALTER TABLE warehouse.dim_empresa ADD CONSTRAINT uq_dim_empresa
    UNIQUE NULLS NOT DISTINCT (nome_fantasia, segmento_de_mercado);
COMMIT;
