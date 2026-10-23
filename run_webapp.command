#!/usr/bin/env bash
# Double-click on macOS, or run from Terminal. Local synthetic demo only.
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
  echo "Docker Desktop belum terpasang atau belum berjalan. Jalankan Docker Desktop lalu coba lagi."
  exit 1
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 belum tersedia. Pasang Python 3 lalu coba lagi."
  exit 1
fi
if [ ! -f .env.local-demo ]; then
  python3 scripts/generate-keys.py --local-demo
fi

compose=(docker compose --env-file .env.local-demo -f docker-compose.yml -f deploy/compose.demo.yml -f deploy/compose.smoke.yml --profile demo)
"${compose[@]}" config --quiet
echo "Menyiapkan dan menjalankan Mapauto Demo Mode..."
"${compose[@]}" up -d --build

if ! "${compose[@]}" exec -T api python -m backend.app.cli admin-exists; then
  echo "Buat akun admin Web App. Password diketik di terminal dan tidak ditampilkan."
  "${compose[@]}" exec api python -m backend.app.cli create-admin
fi
"${compose[@]}" exec -T api python -m backend.app.cli seed-demo

url=http://127.0.0.1:18080
echo "Menunggu Web App siap..."
for attempt in {1..30}; do
  if curl --silent --fail --output /dev/null "$url/api/health"; then
    echo "Mapauto Demo Mode siap: $url"
    open "$url"
    exit 0
  fi
  sleep 2
done
echo "Web App belum merespons. Periksa: ${compose[*]} ps"
exit 1
