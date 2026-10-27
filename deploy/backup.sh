#!/usr/bin/env bash
# Sauvegarde quotidienne de PostgreSQL (à mettre dans la crontab du VPS) :
#   0 4 * * * /opt/wow-forever/deploy/backup.sh >> /var/log/wow-backup.log 2>&1
# Copie hors du VPS : décommenter la ligne rclone en bas après avoir configuré un remote.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
BACKUP_DIR="${BACKUP_DIR:-$HERE/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
STAMP="$(date +%Y-%m-%d_%H%M)"

mkdir -p "$BACKUP_DIR"
cd "$HERE"

# shellcheck disable=SC1091
set -a; . ./.env; set +a

docker compose exec -T db pg_dump -U "${POSTGRES_USER:-wow}" -d "${POSTGRES_DB:-wow}" --no-owner \
  | gzip -9 > "$BACKUP_DIR/wow_$STAMP.sql.gz"

find "$BACKUP_DIR" -name 'wow_*.sql.gz' -mtime +"$RETENTION_DAYS" -delete

echo "$(date -Is) sauvegarde ok : wow_$STAMP.sql.gz"

# rclone copy "$BACKUP_DIR" remote:wow-forever-backups --max-age 2d
