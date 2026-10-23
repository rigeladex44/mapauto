#!/usr/bin/env bash
# Restores ONLY to a new disposable database, never over an existing database.
set -euo pipefail
: "${BACKUP_FILE:?Set encrypted backup file}"
: "${AGE_IDENTITY_FILE:?Set private age identity file path}"
: "${RESTORE_TEST_DATABASE:?Set a NEW restoretest_ database name}"
[[ "$RESTORE_TEST_DATABASE" =~ ^restoretest_[a-z0-9_]+$ ]] || { echo 'Name must start restoretest_' >&2; exit 1; }
cd "$(dirname "$0")/.."
docker compose -f docker-compose.yml exec -T db createdb -U mapauto "$RESTORE_TEST_DATABASE"
age --decrypt -i "$AGE_IDENTITY_FILE" "$BACKUP_FILE" \
 | docker compose -f docker-compose.yml exec -T db pg_restore -U mapauto -d "$RESTORE_TEST_DATABASE" --exit-on-error --no-owner
printf 'Restore completed into isolated database. Review rows/schema before deleting test DB manually.\n'
