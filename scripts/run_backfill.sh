#!/usr/bin/env bash

set -Eeuo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$PROJECT_DIR/.venv/bin/python"

LOG_DIR="$PROJECT_DIR/logs"
LOCK_FILE="/tmp/ecommerce-backfill.lock"

mkdir -p "$LOG_DIR"

exec 9>"$LOCK_FILE"

if ! flock -n 9; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') | Outra execução do backfill está em andamento."
    exit 0
fi

cd "$PROJECT_DIR"

echo "============================================================"
echo "Iniciando backfill: $(date '+%Y-%m-%d %H:%M:%S')"
echo "============================================================"

"$PYTHON" -m src.ingestion.backfill \
    --year 2026 \
    --start-month 5 \
    --end-month 6 \
    --delay 5

echo "Backfill finalizado: $(date '+%Y-%m-%d %H:%M:%S')"