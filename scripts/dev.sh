#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# Activate your web venv before calling. No legacy data is read.
alembic -c backend/alembic.ini upgrade head
uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --no-access-log --no-proxy-headers
