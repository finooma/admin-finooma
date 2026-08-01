#!/usr/bin/env bash
set -euo pipefail

# Run from the directory containing docker-compose.yml.
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BACKUP_DIR="$PROJECT_DIR/backups"
STAMP="$(date +%Y-%m-%d_%H-%M-%S)"
CONTAINER_TMP="/tmp/daftar.sqlite3.$STAMP"
mkdir -p "$BACKUP_DIR"
cd "$PROJECT_DIR"

# SQLite's online backup API creates a consistent snapshot without stopping Gunicorn.
docker compose exec -T daftar python -c "import sqlite3; src=sqlite3.connect('/data/daftar.sqlite3'); dst=sqlite3.connect('$CONTAINER_TMP'); src.backup(dst); dst.close(); src.close()"
docker compose cp "daftar:$CONTAINER_TMP" "$BACKUP_DIR/daftar-$STAMP.sqlite3"
docker compose exec -T daftar rm -f "$CONTAINER_TMP"

# Keep 12 weekly snapshots locally; copy older snapshots to separate storage too.
find "$BACKUP_DIR" -type f -name 'daftar-*.sqlite3' -mtime +84 -delete
echo "Backup created: $BACKUP_DIR/daftar-$STAMP.sqlite3"
