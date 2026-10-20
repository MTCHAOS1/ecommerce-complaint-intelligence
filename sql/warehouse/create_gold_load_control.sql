-- ============================================================
-- E-COMMERCE COMPLAINT INTELLIGENCE PLATFORM
-- Controle de execuções da camada Gold
-- ============================================================

CREATE SCHEMA IF NOT EXISTS metadata;

CREATE TABLE IF NOT EXISTS metadata.gold_load_control (
    execution_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    periodo DATE NOT NULL,

    status VARCHAR(20) NOT NULL,

    registros_staging BIGINT,
    registros_gold BIGINT,

    iniciado_em TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finalizado_em TIMESTAMPTZ,

    mensagem_erro TEXT,

    CONSTRAINT ck_gold_status
        CHECK (status IN ('RUNNING', 'SUCCESS', 'FAILED')),

    CONSTRAINT ck_gold_periodo
        CHECK (EXTRACT(DAY FROM periodo) = 1),

    CONSTRAINT ck_gold_registros_staging
        CHECK (registros_staging >= 0),

    CONSTRAINT ck_gold_registros_gold
        CHECK (registros_gold >= 0)
);

CREATE INDEX IF NOT EXISTS idx_gold_load_control_periodo
    ON metadata.gold_load_control (periodo);

CREATE INDEX IF NOT EXISTS idx_gold_load_control_status
    ON metadata.gold_load_control (status);