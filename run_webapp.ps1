# Local synthetic demo only. Called by run_webapp.bat on Windows.
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
function Fail($message) { Write-Host $message -ForegroundColor Red; exit 1 }
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { Fail 'Docker Desktop belum terpasang.' }
docker info *> $null
if ($LASTEXITCODE -ne 0) { Fail 'Docker Desktop belum berjalan. Jalankan lalu coba lagi.' }
$python = if (Get-Command py -ErrorAction SilentlyContinue) { 'py' } elseif (Get-Command python -ErrorAction SilentlyContinue) { 'python' } else { Fail 'Python 3 belum tersedia.' }
$pythonArgs = if ($python -eq 'py') { @('-3') } else { @() }
if (-not (Test-Path .env.local-demo)) {
    & $python @pythonArgs scripts/generate-keys.py --local-demo
    if ($LASTEXITCODE -ne 0) { Fail 'Gagal membuat konfigurasi demo.' }
}
$composeArgs = @('compose', '--env-file', '.env.local-demo', '-f', 'docker-compose.yml', '-f', 'deploy/compose.demo.yml', '-f', 'deploy/compose.smoke.yml', '--profile', 'demo')
docker @composeArgs config --quiet
if ($LASTEXITCODE -ne 0) { Fail 'Konfigurasi Docker Compose tidak valid.' }
Write-Host 'Menyiapkan dan menjalankan Mapauto Demo Mode...'
docker @composeArgs up -d --build
if ($LASTEXITCODE -ne 0) { Fail 'Gagal menjalankan container. Periksa pesan Docker di atas.' }
docker @composeArgs exec -T api python -m backend.app.cli admin-exists
if ($LASTEXITCODE -ne 0) {
    Write-Host 'Buat akun admin Web App. Password diketik di terminal dan tidak ditampilkan.'
    docker @composeArgs exec api python -m backend.app.cli create-admin
    if ($LASTEXITCODE -ne 0) { Fail 'Gagal membuat admin.' }
}
docker @composeArgs exec -T api python -m backend.app.cli seed-demo
if ($LASTEXITCODE -ne 0) { Fail 'Gagal menyiapkan merchant demo.' }
$url = 'http://127.0.0.1:18080'
Write-Host 'Menunggu Web App siap...'
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    try {
        $response = Invoke-WebRequest -Uri "$url/api/health" -UseBasicParsing -TimeoutSec 3
        if ($response.StatusCode -eq 200) {
            Write-Host "Mapauto Demo Mode siap: $url"
            Start-Process $url
            exit 0
        }
    } catch { Start-Sleep -Seconds 2 }
}
Fail "Web App belum merespons. Periksa: docker compose ps"
