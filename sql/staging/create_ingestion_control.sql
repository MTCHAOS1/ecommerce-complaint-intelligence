CREATE SCHEMA IF NOT EXISTS metadata;

CREATE TABLE IF NOT EXISTS metadata.ingestion_control (
    period VARCHAR(7) PRIMARY KEY,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    attempts INTEGER NOT NULL DEFAULT 0,
    last_attempt TIMESTAMPTZ,
    downloaded_at TIMESTAMPTZ,
    error_message TEXT,
    object_key TEXT,

    CONSTRAINT chk_ingestion_status
    CHECK (
        status IN ('PENDING', 'DOWNLOADED', 'FAILED')
    )
);

CREATE INDEX IF NOT EXISTS idx_ingestion_control_status
ON metadata.ingestion_control(status);