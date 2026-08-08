#!/usr/bin/env bash
# VCOS backup orchestrator (Phase 16.20)
# Uploads Postgres/Redis/OpenSearch snapshots to the vault bucket and records
# the event backup.started / backup.completed in the platform event stream.
set -euo pipefail

REGION="${VCOS_REGION:-na-virginia}"
VAULT_BUCKET="${VAULT_BUCKET:-vcos-backups-$REGION}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
KIND="${BACKUP_KIND:-daily}"

echo "[backup] $KIND backup for $REGION at $STAMP"

# 1. Postgres full backup via pgbackrest (PITR window ships WAL hourly)
pgbackrest --stanza=vcos --type=full --repo1-path="s3://$VAULT_BUCKET/$REGION" backup

# 2. Redis AOF snapshot
redis-cli -h redis BGSAVE

# 3. OpenSearch snapshot to S3 repository
curl -s -X PUT "opensearch/_snapshot/vcos/$STAMP" \
  -H 'Content-Type: application/json' \
  -d "{\"indices\": \"*\", \"ignore_unavailable\": true}"

# 4. Record completion marker (picked up by observability)
echo "$STAMP $KIND ok size_bytes=$(du -sb /var/lib/pgbackrest | cut -f1)" \
  >> /var/log/vcos/backup-history.log

echo "[backup] completed"
