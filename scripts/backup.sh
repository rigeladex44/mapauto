#!/usr/bin/env bash
# Streaming encrypted backup. No plaintext dump is written to disk.
set -euo pipefail
umask 077
cd "$(dirname "$0")/.."
: "${BACKUP_RECIPIENT:?Set an age public recipient, never a private key}"
command -v age >/dev/null || { echo 'Install age before backup' >&2; exit 1; }
backup_dir="${BACKUP_DIR:-./backups}"
mkdir -p "$backup_dir"
backup_file="$backup_dir/mapauto-$(date -u +%Y%m%dT%H%M%SZ).dump.age"
trap 'rm -f "$backup_file.partial"' EXIT
docker compose -f docker-compose.yml exec -T db pg_dump -U mapauto -d mapauto -Fc \
  | age -r "$BACKUP_RECIPIENT" -o "$backup_file.partial"
test -s "$backup_file.partial"
mv "$backup_file.partial" "$backup_file"
sha256sum "$backup_file" > "$backup_file.sha256"
printf 'Encrypted backup created; verify off-host copy and test restore.\n'
