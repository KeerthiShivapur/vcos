#!/usr/bin/env bash
# VCOS restore (Phase 16.20) - point-in-time recovery
# Usage: restore-script.sh <backup-stamp|PITR-TIMESTAMP>
set -euo pipefail

REGION="${VCOS_REGION:-na-virginia}"
VAULT_BUCKET="${VAULT_BUCKET:-vcos-backups-$REGION}"
TARGET="${1:?usage: restore-script.sh <stamp|ISO-timestamp>}"

echo "[restore] target=$TARGET region=$REGION"

# Phase 16 PITR flow:
#   1. spin up a restore instance from the latest base backup
#   2. replay WAL up to the requested timestamp (recovery_target_time)
#   3. validate checksums, then promote the restore instance
pgbackrest --stanza=vcos --type=standby \
  --target-time="$TARGET" \
  --target-action=promote \
  --repo1-path="s3://$VAULT_BUCKET/$REGION" \
  restore

# Health gate: the DB must answer before traffic is cut over
until pg_isready -h "$RESTORE_HOST" -t 5; do sleep 5; done
psql -h "$RESTORE_HOST" -c "SELECT pg_is_in_recovery();" | grep -q f || { echo "replica still in recovery"; exit 1; }

echo "[restore] complete - promote DNS to $RESTORE_HOST"
