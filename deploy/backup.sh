#!/usr/bin/env bash
# Daily PostgreSQL backup. TEST RESTORE REGULARLY — an untested backup is not a backup.
set -euo pipefail
STAMP=$(date +%F-%H%M)
OUT=/opt/romka/backups/romka-$STAMP.dump
mkdir -p /opt/romka/backups
set -a; . /opt/romka/.env; set +a
PGPASSWORD="$(python3 -c "import os,urllib.parse as u;print(u.urlparse(os.environ['DATABASE_URL']).password or '')")"
export PGPASSWORD
pg_dump -h localhost -U romka -d romka -Fc -f "$OUT"
sha256sum "$OUT" > "$OUT.sha256"
find /opt/romka/backups -name 'romka-*.dump' -mtime +14 -delete
echo "backup: $OUT"
# Restore drill (run manually in a scratch DB):
#   createdb romka_restore && pg_restore -d romka_restore /opt/romka/backups/romka-XXXX.dump
