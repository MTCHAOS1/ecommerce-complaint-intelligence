ALTER TABLE metadata.ingestion_control
ADD COLUMN IF NOT EXISTS source_status VARCHAR(30);

ALTER TABLE metadata.ingestion_control
ADD COLUMN IF NOT EXISTS source_checked_at TIMESTAMPTZ;