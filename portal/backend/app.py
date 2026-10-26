import asyncio
import contextlib
import hashlib
import hmac
import os
import secrets
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, SecretStr
from .merchant import Merchant, MerchantError, HumanRequired
from .policy import Mode, parse_niks
from .store import Store

FRONTEND = Path(__file__).resolve().parents[1] / 'frontend'

def now():
    return datetime.now(timezone.utc).isoformat()

class Login(BaseModel):
    access_key: SecretStr
    identity: str = Field(min_length=3, max_length=150)
    pin: SecretStr

class BatchInput(BaseModel):
    niks: list[str]
    mode: Mode
    speed: str = Field(pattern='^(Normal|Kalem)$', default='Normal')

class Control(BaseModel):
    action: str = Field(pattern='^(pause|resume|stop)$')

class Session:
    def __init__(self, account_key, adapter):
        self.id = secrets.token_urlsafe(32)
        self.account_key = account_key
        self.adapter = adapter
        self.state = 'Menghubungkan'
        self.message = ''
        self.created = time.monotonic()
        self.last = self.created
        self.name = self.subname = None
        self.stock = None
        self.last_sync = None
        self.task = None
        self.batch = None
        self.lock = asyncio.Lock()
        self.closed = False
        self.pause = False
        self.stop = False
        self.gate = asyncio.Event()
        self.gate.set()

    def public(self):
        return {'state': self.state, 'message': self.message, 'name': self.name,
                'subname': self.subname, 'stock': self.stock, 'last_sync': self.last_sync,
                'batch_id': self.batch['id'] if self.batch else None,
                'test_mode': 'inspection_only', 'headless': getattr(self.adapter, 'heading', True)}


def create_app(adapter_factory=Merchant, db_path=None, access_key=None):
    sessions = {}
    key = access_key if access_key is not None else os.getenv('MAP_ACCESS_KEY', '')
    store_path = db_path or os.getenv('MAP_DB_PATH', str(Path(__file__).resolve().parents[1] / 'runtime/map-pro.sqlite3'))
    store = None

    async def dispose(s):
        if s.closed:
            return
        s.closed = True
        if active(s):
            s.batch['state'] = 'Terputus'
            for row in s.batch['rows']:
                if row['status'] == 'Diproses':
                    row.update(status='Perlu diperiksa', reason='Sesi ditutup saat inspeksi. Tidak ada transaksi dikirim.', stage='')
            store.save(s.id, s.batch)
        if s.task and not s.task.done():
            s.task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await s.task
        with contextlib.suppress(Exception):
            await s.adapter.close()
        sessions.pop(s.id, None)

    async def reap():
        while True:
            await asyncio.sleep(60)
            for s in list(sessions.values()):
                if (time.monotonic() - s.last > 1800 and not active(s)) or time.monotonic() - s.created > 8 * 3600:
                    await dispose(s)

    @asynccontextmanager
    async def lifespan(app):
        nonlocal store
        if len(key) < 24:
            raise RuntimeError('Set MAP_ACCESS_KEY dengan minimal 24 karakter acak sebelum menjalankan backend.')
        store = Store(store_path)
        cleaner = asyncio.create_task(reap())
        yield
        cleaner.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await cleaner
        for s in list(sessions.values()):
            await dispose(s)
        store.close()

    app = FastAPI(title='MAP.PRO — Playwright inspection API', lifespan=lifespan)
    origins = [x.strip() for x in os.getenv('MAP_ALLOWED_ORIGINS', '').split(',') if x.strip()]
    if '*' in origins:
        raise RuntimeError('MAP_ALLOWED_ORIGINS harus berisi origin frontend yang spesifik.')
    if origins:
        app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=['GET', 'POST'],
                           allow_headers=['Authorization', 'Content-Type'])

    @app.middleware('http')
    async def protect(request: Request, call_next):
        # Cookie-free bearer auth; reject browser cross-origin requests not explicitly allowed.
        origin = request.headers.get('origin')
        same = str(request.base_url).rstrip('/')
        if origin and origin != same and origin not in origins:
            return PlainTextResponse('Origin tidak diizinkan.', status_code=403)
        # Avoid returning raw request bodies in validation errors (credentials/NIK).
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        return response

    from fastapi.exceptions import RequestValidationError
    @app.exception_handler(RequestValidationError)
    async def invalid(request, exc):
        from fastapi.responses import JSONResponse
        return JSONResponse({'detail': 'Format permintaan tidak valid.'}, status_code=422)

    def auth(request):
        token = request.headers.get('Authorization', '').removeprefix('Bearer ')
        s = sessions.get(token)
        if not s or s.closed or time.monotonic() - s.created > 8 * 3600:
            raise HTTPException(401, 'Sesi aplikasi berakhir. Login ulang.')
        s.last = time.monotonic()
        return s

    def active(s):
        return s.batch is not None and s.batch['state'] in ('Berjalan', 'Dijeda', 'Menghentikan')

    def require_ready(s):
        if s.state != 'Terhubung':
            raise HTTPException(409, s.message or 'Sesi merchant belum siap.')

    async def refresh(s):
        # Preserve last known stock if extraction fails, with a visible stale marker.
        try:
            s.stock = await s.adapter.stock()
            s.last_sync = now()
            s.message = ''
        except HumanRequired as exc:
            s.state, s.message = 'Perlu verifikasi', str(exc)
        except Exception:
            s.message = 'Stok belum tersinkron. Nilai terakhir dipertahankan.'
        return s.public()

    async def _finish_login(s, body):
        try:
            await s.adapter.login(body.identity, body.pin.get_secret_value())
            meta = await s.adapter.dashboard()
            s.name, s.subname = meta['name'], meta['subname']
            s.state = 'Terhubung'
            await refresh(s)
        except HumanRequired as exc:
            s.state, s.message = 'Perlu verifikasi', str(exc)
        except Exception:
            s.state, s.message = 'Login gagal', 'Login belum berhasil. Periksa browser dan kredensial merchant.'
        finally:
            # Delete transient credentials from the model after one login attempt.
            body.pin = SecretStr('')
            body.access_key = SecretStr('')
            body.identity = ''

    async def finish_login(s, body):
        async with s.lock:
            await _finish_login(s, body)

    # Basic bounded in-memory throttle; add reverse-proxy rate limits for internet hosting.
    login_attempts = {}
    @app.post('/api/login', status_code=202)
    async def login(body: Login, request: Request):
        address = request.client.host if request.client else 'unknown'
        attempts = [t for t in login_attempts.get(address, []) if time.monotonic() - t < 60]
        if len(attempts) >= 6:
            raise HTTPException(429, 'Terlalu banyak percobaan. Tunggu satu menit.')
        attempts.append(time.monotonic())
        login_attempts[address] = attempts
        if not hmac.compare_digest(body.access_key.get_secret_value(), key):
            raise HTTPException(401, 'Kunci akses aplikasi tidak valid.')
        if not body.pin.get_secret_value() or len(body.pin.get_secret_value()) > 64:
            raise HTTPException(422, 'PIN wajib diisi.')
        account_key = hashlib.sha256(body.identity.strip().casefold().encode()).hexdigest()
        if any(s.account_key == account_key for s in sessions.values()):
            raise HTTPException(409, 'Akun ini sudah memiliki sesi aktif. Logout atau tunggu sesi berakhir.')
        if len(sessions) >= int(os.getenv('MAP_MAX_SESSIONS', '2')):
            raise HTTPException(429, 'Kapasitas browser penuh.')
        s = Session(account_key, adapter_factory())
        sessions[s.id] = s
        s.task = asyncio.create_task(finish_login(s, body))
        return {'session_token': s.id, **s.public()}

    @app.get('/api/session')
    async def session(request: Request):
        return auth(request).public()

    @app.post('/api/session/check')
    async def check(request: Request):
        s = auth(request)
        if active(s) or (s.task and not s.task.done()):
            raise HTTPException(409, 'Masih ada proses aktif.')
        async with s.lock:
            try:
                await s.adapter.wait_login()
                meta = await s.adapter.dashboard()
                s.name, s.subname = meta['name'], meta['subname']
                s.state, s.message = 'Terhubung', ''
                return await refresh(s)
            except HumanRequired as exc:
                s.state, s.message = 'Perlu verifikasi', str(exc)
                return s.public()
            except Exception:
                raise HTTPException(409, 'Sesi belum terkonfirmasi; periksa browser pengujian.')

    @app.post('/api/stock/sync')
    async def sync_stock(request: Request):
        s = auth(request)
        require_ready(s)
        if active(s) or s.lock.locked():
            raise HTTPException(409, 'Tunggu batch/jeda inspeksi selesai sebelum sinkronisasi.')
        async with s.lock:
            return await refresh(s)

    async def worker(s):
        data = s.batch
        async with s.lock:
            for row in data['rows']:
                await s.gate.wait()
                if s.stop:
                    break
                row.update(status='Diproses', stage='Membuka pemeriksaan NIK')
                store.save(s.id, data)
                async def emit(stage):
                    row['stage'] = stage
                    store.save(s.id, data)
                try:
                    result = await s.adapter.prepare(row['nik'], data['mode'], emit)
                    row.update(result)
                except HumanRequired as exc:
                    row.update(status='Perlu verifikasi', reason=str(exc))
                    s.state, s.message = 'Perlu verifikasi', str(exc)
                    s.stop = True
                except Exception:
                    row.update(status='Perlu diperiksa', reason='Tampilan merchant belum terkonfirmasi. Tidak ada transaksi dikirim.')
                    s.stop = True
                row.update(stage='', finishedAt=now(), qty=0)
                store.save(s.id, data)
                if s.stop:
                    break
                await asyncio.sleep(2 if data['speed'] == 'Kalem' else .3)
            data['state'] = 'Dihentikan' if s.stop else 'Selesai'
            data['finished'] = now()
            store.save(s.id, data)
            # Keep /sale visible for the operator. Stock is read only on an explicit sync.

    @app.post('/api/batches', status_code=202)
    async def start_batch(body: BatchInput, request: Request):
        s = auth(request)
        require_ready(s)
        if active(s) or s.lock.locked():
            raise HTTPException(409, 'Hanya satu proses aktif per akun.')
        try:
            niks = parse_niks(body.niks)
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        data = {'id': secrets.token_urlsafe(16), 'started': now(), 'finished': None,
                'mode': body.mode.value, 'speed': body.speed, 'state': 'Berjalan',
                'test_mode': 'inspection_only', 'rows': [{'nik': n, 'status': 'Menunggu', 'type': '—',
                    'qty': 0, 'reason': '', 'stage': ''} for n in niks]}
        s.batch, s.pause, s.stop = data, False, False
        s.gate.set()
        store.save(s.id, data)
        s.task = asyncio.create_task(worker(s))
        return data

    @app.get('/api/batches')
    async def batches(request: Request):
        s = auth(request)
        return store.list(s.id)

    @app.get('/api/batches/{bid}')
    async def get_batch(bid: str, request: Request):
        s = auth(request)
        data = store.get(s.id, bid)
        if not data:
            raise HTTPException(404, 'Batch tidak ditemukan.')
        return data

    @app.post('/api/batches/{bid}/control')
    async def control_batch(bid: str, body: Control, request: Request):
        s = auth(request)
        if not s.batch or s.batch['id'] != bid or not active(s):
            raise HTTPException(409, 'Batch tidak aktif.')
        if s.stop:
            raise HTTPException(409, 'Batch sedang dihentikan.')
        if body.action == 'pause':
            s.pause = True
            s.gate.clear()
            s.batch['state'] = 'Dijeda'
        elif body.action == 'resume':
            s.pause = False
            s.gate.set()
            s.batch['state'] = 'Berjalan'
        else:
            s.stop = True
            s.gate.set()
            s.batch['state'] = 'Menghentikan'
        store.save(s.id, s.batch)
        return s.batch

    @app.post('/api/logout')
    async def logout(request: Request):
        s = auth(request)
        if active(s) or s.lock.locked() or (s.task and not s.task.done()):
            raise HTTPException(409, 'Selesaikan/hentikan proses aktif terlebih dahulu.')
        await dispose(s)
        return {'ok': True}

    @app.get('/api/health')
    async def health():
        return {'ok': True, 'test_mode': 'inspection_only', 'transactions_enabled': False}

    @app.get('/')
    async def index():
        return FileResponse(FRONTEND / 'index.html')

    app.mount('/assets', StaticFiles(directory=FRONTEND / 'assets'), name='assets')
    app.mount('/', StaticFiles(directory=FRONTEND, html=True), name='frontend')
    return app

app = create_app()
