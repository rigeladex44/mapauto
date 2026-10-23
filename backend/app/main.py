import csv, io, secrets, time
from urllib.parse import urlsplit
from pathlib import Path
from fastapi import FastAPI, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, func, delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DB
from starlette.middleware.trustedhost import TrustedHostMiddleware
from .config import settings
from .db import get_db
from .models import User, Session, Merchant, Job, Worker, Audit, SystemSetting, MerchantGrant
from .security import current_user, require, hash_password, verify_password, token_hash
from .schemas import Login, UserCreate, UserUpdate, PasswordChange, MerchantInput, JobInput, WorkerInput, SystemInput
from .domain import validate_filters, extend_expiry, stock_summary

cfg=settings()
app=FastAPI(title='Mapauto API',docs_url='/api/docs' if cfg.app_env!='production' else None,redoc_url=None)
from .limits import RequestLimitMiddleware
app.add_middleware(RequestLimitMiddleware)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=cfg.allowed_hosts.split(','))
@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    # Do not echo passwords or credential-like input back to clients/logs.
    return JSONResponse(status_code=422,content={'detail':'Input tidak valid. Periksa format dan batas panjang kolom.'})

DUMMY_HASH=hash_password(secrets.token_urlsafe(24))

def log(db, actor, action, target):
    db.add(Audit(actor_id=actor.id if actor else None, action=action,target=str(target)))
def public_user(u):
    return dict(id=u.id,username=u.username,role=u.role,active=u.active,expires_at=u.expires_at,tenant_id=u.tenant_id)
def merchant_dict(m):
    return {k:getattr(m,k) for k in ('id','name','reference','authorized','active','filters','stock','stock_at','stock_simulated')}
def job_dict(j):
    return {k:getattr(j,k) for k in ('id','merchant_id','kind','status','simulated','quantity','created_at','updated_at','worker_id','result','batch_id','nik_masked','phase')}
def commit(db):
    try: db.commit()
    except IntegrityError:
        db.rollback(); raise HTTPException(409,'Data sudah ada atau konflik perubahan')

@app.middleware('http')
async def headers(request, call_next):
    if request.method not in ('GET','HEAD','OPTIONS'):
        origin=request.headers.get('origin')
        if request.headers.get('sec-fetch-site')=='cross-site' or (origin and urlsplit(origin).netloc!=request.headers.get('host')):
            return JSONResponse(status_code=403,content={'detail':'Cross-site request ditolak'})
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='no-referrer'
    response.headers['X-Frame-Options']='DENY'
    response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    if request.url.path.startswith('/api'): response.headers['Cache-Control']='no-store'
    if cfg.cookie_secure: response.headers['Strict-Transport-Security']='max-age=31536000; includeSubDomains'
    return response

@app.get('/api/health')
def health(db: DB=Depends(get_db)):
    db.execute(select(func.count(User.id)))
    if cfg.app_env=='production' or cfg.rate_limit_enabled:
        from .queue import connection
        try:connection().ping()
        except Exception:raise HTTPException(503,'Queue belum siap')
    return {'status':'ok','demo_mode':cfg.demo_mode,'live_integration':False}

@app.post('/api/auth/login')
def login(data: Login,response: Response,db: DB=Depends(get_db)):
    user=db.scalar(select(User).where(User.username==data.username.lower()).with_for_update())
    now=time.time()
    valid=verify_password(data.password,user.password_hash if user else DUMMY_HASH)
    if user and user.locked_until>now: raise HTTPException(429,'Terlalu banyak percobaan. Coba lagi nanti')
    if not valid or not user or not user.active or (user.expires_at is not None and user.expires_at<=now):
        if user:
            user.failed_logins+=1
            if user.failed_logins>=5: user.locked_until=now+300
        log(db,None,'login.failed','redacted'); db.commit()
        raise HTTPException(401,'Username, password atau masa aktif tidak valid')
    user.failed_logins=0; user.locked_until=0
    db.execute(delete(Session).where(Session.expires_at<now))
    token=secrets.token_urlsafe(32); csrf=secrets.token_urlsafe(32)
    db.add(Session(token_hash=token_hash(token),user_id=user.id,csrf=csrf,expires_at=now+cfg.session_hours*3600))
    log(db,user,'login','session'); db.commit()
    response.set_cookie('mapauto_session',token,httponly=True,secure=cfg.cookie_secure,samesite='strict',max_age=cfg.session_hours*3600,path='/')
    return {'user':public_user(user),'csrf':csrf,'demo_mode':cfg.demo_mode}

@app.get('/api/auth/me')
def me(request: Request,user=Depends(current_user)):
    return {'user':public_user(user),'csrf':request.state.session.csrf,'demo_mode':cfg.demo_mode}

@app.post('/api/auth/logout',status_code=204)
def logout(request:Request,response:Response,user=Depends(current_user),db: DB=Depends(get_db)):
    db.delete(request.state.session); log(db,user,'logout','session'); db.commit()
    response.delete_cookie('mapauto_session',path='/')

@app.post('/api/auth/password',status_code=204)
def change_password(data:PasswordChange,user=Depends(current_user),db: DB=Depends(get_db)):
    if not verify_password(data.current_password,user.password_hash): raise HTTPException(400,'Password saat ini salah')
    user.password_hash=hash_password(data.new_password)
    db.execute(delete(Session).where(Session.user_id==user.id))
    log(db,user,'password.changed',user.id); db.commit()

@app.get('/api/dashboard')
def dashboard(user=Depends(current_user),db: DB=Depends(get_db)):
    merchants=db.scalars(select(Merchant).where(Merchant.active.is_(True))).all()
    summary=stock_summary(merchants,include_simulated=cfg.demo_mode)
    summary.update(jobs=db.scalar(select(func.count(Job.id))),running=db.scalar(select(func.count(Job.id)).where(Job.status=='running')),demo_mode=cfg.demo_mode,live_integration=False)
    return summary

@app.get('/api/merchants')
def merchants(user=Depends(current_user),db: DB=Depends(get_db)):
    return [merchant_dict(m) for m in db.scalars(select(Merchant).order_by(Merchant.stock.desc().nullslast(),Merchant.id)).all()]

@app.post('/api/merchants',status_code=201)
def create_merchant(data: MerchantInput,user=Depends(require('admin','operator')),db: DB=Depends(get_db)):
    try: validate_filters(data.filters)
    except ValueError: raise HTTPException(422,'Filter pelanggan tidak valid')
    m=Merchant(**data.model_dump()); db.add(m)
    try:db.flush()
    except IntegrityError:db.rollback();raise HTTPException(409,'Referensi merchant sudah ada')
    if user.role!='admin':
        db.add(MerchantGrant(tenant_id=user.tenant_id,user_id=user.id,merchant_id=m.id))
        db.info['merchant_ids'].append(m.id)
    log(db,user,'merchant.created','metadata'); commit(db); return merchant_dict(m)

@app.put('/api/merchants/{merchant_id}')
def update_merchant(merchant_id:int,data:MerchantInput,user=Depends(require('admin','operator')),db: DB=Depends(get_db)):
    m=db.get(Merchant,merchant_id)
    if not m: raise HTTPException(404,'Merchant tidak ditemukan')
    try: validate_filters(data.filters)
    except ValueError: raise HTTPException(422,'Filter pelanggan tidak valid')
    if data.active!=m.active and user.role!='admin': raise HTTPException(403,'Hanya admin dapat mengaktifkan/menonaktifkan merchant')
    for k,v in data.model_dump().items(): setattr(m,k,v)
    if not m.active or not m.authorized:
        for j in db.scalars(select(Job).where(Job.merchant_id==m.id,Job.status.in_(['queued','running','WAITING_VERIFICATION']))):
            j.status='RECONCILIATION_REQUIRED' if j.phase=='submitting' else 'cancelled'; j.updated_at=time.time(); j.result='Otorisasi merchant dinonaktifkan; tinjau status bila pengiriman sudah dimulai'
    log(db,user,'merchant.updated',m.id); commit(db); return merchant_dict(m)

@app.get('/api/users')
def users(user=Depends(require('admin')),db: DB=Depends(get_db)):
    return [{**public_user(u),'merchant_ids':list(db.scalars(select(MerchantGrant.merchant_id).where(MerchantGrant.user_id==u.id)))} for u in db.scalars(select(User).order_by(User.id))]

@app.post('/api/users',status_code=201)
def create_user(data:UserCreate,user=Depends(require('admin')),db: DB=Depends(get_db)):
    u=User(username=data.username.lower(),password_hash=hash_password(data.password),role=data.role,expires_at=time.time()+30*86400)
    db.add(u); log(db,user,'user.created','account'); commit(db); return public_user(u)

@app.put('/api/users/{user_id}')
def update_user(user_id:int,data:UserUpdate,user=Depends(require('admin')),db: DB=Depends(get_db)):
    u=db.get(User,user_id)
    if not u: raise HTTPException(404,'Pengguna tidak ditemukan')
    if u.id==user.id and (not data.active or data.role!='admin'): raise HTTPException(400,'Tidak dapat menonaktifkan atau menurunkan akses sendiri')
    u.role=data.role; u.active=data.active
    if data.extend_days: u.expires_at=extend_expiry(u.expires_at,time.time(),data.extend_days)
    db.execute(delete(Session).where(Session.user_id==u.id))
    log(db,user,'user.updated',u.id); commit(db); return public_user(u)

@app.get('/api/jobs')
def jobs(user=Depends(current_user),db: DB=Depends(get_db)):
    return [job_dict(j) for j in db.scalars(select(Job).order_by(Job.id.desc()).limit(200))]

@app.post('/api/jobs',status_code=201)
def create_job(data:JobInput,user=Depends(require('admin','operator')),db: DB=Depends(get_db)):
    if not data.simulated: raise HTTPException(409,'Integrasi merchant resmi belum dikonfigurasi; transaksi live ditolak')
    if not cfg.demo_mode: raise HTTPException(409,'Simulasi hanya tersedia dalam Demo Mode')
    m=db.get(Merchant,data.merchant_id)
    if not m or not m.active or not m.authorized: raise HTTPException(400,'Merchant harus aktif dan diotorisasi')
    j=Job(**data.model_dump(),created_by=user.id); db.add(j)
    log(db,user,'job.queued',data.kind); commit(db); return job_dict(j)

@app.post('/api/jobs/{job_id}/cancel')
def cancel_job(job_id:int,user=Depends(require('admin','operator')),db: DB=Depends(get_db)):
    j=db.scalar(select(Job).where(Job.id==job_id).with_for_update())
    if not j: raise HTTPException(404,'Job tidak ditemukan')
    if j.status not in ('queued','running','WAITING_VERIFICATION'): raise HTTPException(409,'Job sudah selesai')
    j.status='RECONCILIATION_REQUIRED' if j.phase=='submitting' else 'cancelled'; j.updated_at=time.time(); j.result='Tinjau status pengiriman sebelum tindakan berikutnya' if j.phase=='submitting' else 'Dibatalkan oleh operator'
    log(db,user,'job.cancelled',j.id); db.commit(); return job_dict(j)

@app.get('/api/workers')
def workers(user=Depends(current_user),db: DB=Depends(get_db)):
    return [dict(id=w.id,heartbeat=w.heartbeat,paused=w.paused,online=time.time()-w.heartbeat<20) for w in db.scalars(select(Worker))]

@app.put('/api/workers/{worker_id}')
def update_worker(worker_id:str,data:WorkerInput,user=Depends(require('admin','operator')),db: DB=Depends(get_db)):
    w=db.get(Worker,worker_id)
    if not w: raise HTTPException(404,'Worker tidak ditemukan')
    w.paused=data.paused; log(db,user,'worker.paused' if w.paused else 'worker.resumed',w.id); db.commit(); return {'paused':w.paused}

@app.get('/api/logs')
def logs(user=Depends(require('admin','operator')),db: DB=Depends(get_db)):
    return [dict(id=a.id,actor_id=a.actor_id,action=a.action,target=a.target,created_at=a.created_at) for a in db.scalars(select(Audit).where(Audit.actor_id==user.id if user.role!='admin' else True).order_by(Audit.id.desc()).limit(200))]

@app.get('/api/reports/jobs.csv')
def report(user=Depends(require('admin','operator')),db: DB=Depends(get_db)):
    stream=io.StringIO(); writer=csv.writer(stream)
    writer.writerow(['job_id','merchant_id','kind','status','simulated','quantity','created_at'])
    for j in db.scalars(select(Job).order_by(Job.id)):
        writer.writerow([j.id,j.merchant_id,j.kind,j.status,j.simulated,j.quantity,j.created_at])
    log(db,user,'report.exported','jobs'); db.commit()
    return Response(stream.getvalue(),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="mapauto-jobs.csv"','Cache-Control':'no-store'})

@app.get('/api/settings')
def system(user=Depends(require('admin')),db: DB=Depends(get_db)):
    s=db.get(SystemSetting,(user.tenant_id,'notifications'))
    return {'telegram_notifications':bool(s and s.value.get('enabled')), 'telegram_configured':bool(cfg.telegram_enabled and cfg.telegram_bot_token and cfg.telegram_chat_id), 'demo_mode':cfg.demo_mode,'live_integration':False}

@app.put('/api/settings')
def update_system(data:SystemInput,user=Depends(require('admin')),db: DB=Depends(get_db)):
    if data.telegram_notifications and not (cfg.telegram_enabled and cfg.telegram_bot_token and cfg.telegram_chat_id):
        raise HTTPException(409,'Konfigurasi secret Telegram dan opt-in environment diperlukan')
    db.merge(SystemSetting(tenant_id=user.tenant_id,key='notifications',value={'enabled':data.telegram_notifications}))
    log(db,user,'settings.updated','notifications'); db.commit(); return {'saved':True}

from .batch_api import router as batch_router
app.include_router(batch_router)

# Serve only built PWA artifacts, never the repository or runtime data.
dist=Path(__file__).resolve().parents[2]/'webapp'/'dist'
if dist.is_dir():
    app.mount('/assets',StaticFiles(directory=dist/'assets'),name='assets')
    @app.get('/{path:path}',include_in_schema=False)
    def frontend(path:str):
        if path.startswith('api/'): raise HTTPException(404,'Not found')
        allowed={'manifest.webmanifest','sw.js','icon.svg','icon-192.png','icon-512.png','apple-touch-icon.png'}
        return FileResponse(dist/path if path in allowed else dist/'index.html',headers={'Cache-Control':'no-cache'})
