#!/usr/bin/env bash
set -euo pipefail

CONTAINER_NAME="finally"
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

# Stop and remove container, keep volume (idempotent)
docker rm -f "$CONTAINER_NAME" &>/dev/null || true

if [[ "${1:-}" == "--wipe" ]]; then
    DB_FILE="$ROOT_DIR/db/simulated_trading.db"
    if [[ -f "$DB_FILE" ]]; then
        rm "$DB_FILE"
        echo "Removed $DB_FILE."
    fi
fi

echo "FinAlly stopped."
