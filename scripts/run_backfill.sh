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
    exit 1
fi

cd "$PROJECT_DIR"

echo "============================================================"
echo "Iniciando atualização Bronze -> Gold: $(date '+%Y-%m-%d %H:%M:%S')"
echo "============================================================"

# Sem argumentos: três últimos meses encerrados, Bronze até Gold.
# Argumentos explícitos são encaminhados à CLI (incluindo --plan).
"$PYTHON" -m src.ingestion.refresh "$@"

echo "Atualização finalizada: $(date '+%Y-%m-%d %H:%M:%S')"
