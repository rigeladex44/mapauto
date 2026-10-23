"""Isolated Chromium contexts and durable, fenced jobs. Mock adapter only.
No browser debugging ports, VNC, stored merchant passwords, or CAPTCHA solver.
"""
import os, signal, socket, threading, time, uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from sqlalchemy import select
from .db import SessionLocal
from .models import Job, Batch, Merchant, User, Worker, Verification, Audit
from .config import settings
from .crypto import decrypt
from .queue import connection, dispatch

STOP=threading.Event()
ACTIVE={'running','WAITING_VERIFICATION'}
TERMINAL={'succeeded','failed','cancelled','RECONCILIATION_REQUIRED'}

def worker_row(db,root,tenant_id):
    wid=f'{root}:{tenant_id}'
    w=db.get(Worker,wid)
    if not w:
        w=Worker(id=wid,tenant_id=tenant_id,heartbeat=time.time());db.add(w);db.flush()
    return w

def recover():
    """Never replay a submission whose outcome is unknown."""
    now=time.time()
    with SessionLocal() as db:
        for j in db.scalars(select(Job).where(Job.status.in_(list(ACTIVE)),Job.lease_until<now).with_for_update(skip_locked=True)):
            if j.phase=='submitting':
                j.status='RECONCILIATION_REQUIRED';j.result='Pengiriman belum diketahui; rekonsiliasi manual wajib'
            elif j.status=='WAITING_VERIFICATION':
                j.status='failed';j.result='Session verifikasi berakhir saat worker terputus';j.nik_encrypted=None
            else:
                j.status='queued';j.result='Worker terputus sebelum pengiriman; aman masuk antrean kembali'
            j.fencing_token=None;j.updated_at=now
            db.add(Audit(tenant_id=j.tenant_id,action='job.recovered.'+j.status,target=str(j.id)))
        for b in db.scalars(select(Batch).where(Batch.status=='preview',Batch.expires_at<now)):
            b.status='expired'
            for j in db.scalars(select(Job).where(Job.batch_id==b.id,Job.status=='preview')):j.status='cancelled';j.nik_encrypted=None
        for v in db.scalars(select(Verification).where(Verification.expires_at<now)):
            v.response_encrypted=None;v.status='expired' if v.status in ('waiting','responded') else v.status
        db.commit()

@contextmanager
def capacity(r,token):
    # Global across worker processes on the VPS; only opaque lease IDs in Redis.
    script="""redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', ARGV[1]); if redis.call('ZCARD',KEYS[1])>=tonumber(ARGV[3]) then return 0 end;redis.call('ZADD',KEYS[1],ARGV[2],ARGV[4]);return 1"""
    now=time.time();cfg=settings()
    granted=r.eval(script,1,'mapauto:browser-slots',now,now+cfg.worker_lease_seconds,cfg.max_browser_contexts,token)
    try:yield bool(granted)
    finally:
        if granted:r.zrem('mapauto:browser-slots',token)

def run_job(jid,root='browser-worker'):
    cfg=settings();r=connection();token=uuid.uuid4().hex
    with SessionLocal() as db:
        j=db.get(Job,jid)
        if not j or j.status!='queued':return
        merchant_id=j.merchant_id;tenant_id=j.tenant_id
    lock=r.lock(f'mapauto:merchant:{merchant_id}',timeout=cfg.worker_lease_seconds,thread_local=False)
    if not lock.acquire(blocking=False):return
    try:
        with capacity(r,token) as granted:
            if not granted:return
            with SessionLocal() as db:
                # DB row locks serialize claims even if a Redis message is duplicated.
                m=db.scalar(select(Merchant).where(Merchant.id==merchant_id).with_for_update())
                j=db.scalar(select(Job).where(Job.id==jid).with_for_update())
                if j.status!='queued':return
                if db.scalar(select(Job.id).where(Job.merchant_id==merchant_id,Job.id!=jid,Job.status.in_(list(ACTIVE|{'RECONCILIATION_REQUIRED'}))).limit(1)):return
                b=db.get(Batch,j.batch_id) if j.batch_id else None
                if b and b.status!='queued':return
                w=worker_row(db,root,tenant_id)
                if w.paused:return
                creator=db.get(User,j.created_by)
                if not cfg.demo_mode or not j.simulated or not m or m.tenant_id!=tenant_id or not m.authorized or not m.active or not creator or creator.tenant_id!=tenant_id or not creator.active or creator.role not in ('admin','operator') or (creator.expires_at is not None and creator.expires_at<time.time()):
                    j.status='failed';j.result='Mode, otorisasi atau tenant tidak mengizinkan';j.nik_encrypted=None;db.commit();return
                j.status='running';j.worker_id=w.id;j.fencing_token=token;j.lease_until=time.time()+cfg.worker_lease_seconds;j.updated_at=time.time()
                db.commit()
            lost=threading.Event();done=threading.Event()
            def renew():
                while not done.wait(2):
                    try:
                        lock.extend(cfg.worker_lease_seconds,replace_ttl=True)
                        r.zadd('mapauto:browser-slots',{token:time.time()+cfg.worker_lease_seconds})
                        with SessionLocal() as db:
                            q=db.get(Job,jid)
                            if not q or q.fencing_token!=token or q.status not in ACTIVE:lost.set();return
                            q.lease_until=time.time()+cfg.worker_lease_seconds
                            worker_row(db,root,tenant_id).heartbeat=time.time();db.commit()
                    except Exception:lost.set();return
            thread=threading.Thread(target=renew,daemon=True);thread.start()
            try:
                execute_browser(jid,token,lost)
            except Exception:
                # Never log URL, NIK, OTP, cookie, screenshot or exception payload.
                with SessionLocal() as db:
                    q=db.scalar(select(Job).where(Job.id==jid).with_for_update())
                    if q and q.fencing_token==token and q.status in ACTIVE:
                        q.status='RECONCILIATION_REQUIRED' if q.phase=='submitting' else 'failed'
                        q.result='Hasil pengiriman belum diketahui' if q.phase=='submitting' else 'Browser gagal sebelum pengiriman; tidak diulang otomatis'
                        q.updated_at=time.time()
                        if q.status=='failed':q.nik_encrypted=None
                        db.add(Audit(tenant_id=q.tenant_id,action='job.'+q.status,target=str(q.id)));db.commit()
            finally:
                done.set();thread.join(timeout=4)
    finally:
        try:lock.release()
        except Exception:pass

def load_owned(db,jid,token):
    q=db.scalar(select(Job).where(Job.id==jid).with_for_update())
    if not q or q.fencing_token!=token or q.status not in ACTIVE or q.lease_until<time.time():raise RuntimeError('Lease lost')
    m=db.get(Merchant,q.merchant_id);u=db.get(User,q.created_by)
    b=db.get(Batch,q.batch_id) if q.batch_id else None
    if not m or not m.active or not m.authorized or not u or not u.active or u.role not in ('admin','operator') or (u.expires_at is not None and u.expires_at<time.time()) or (b and b.status=='cancelled'):raise RuntimeError('Access revoked')
    return q,m

def execute_browser(jid,token,lost):
    from playwright.sync_api import sync_playwright
    cfg=settings()
    # Only local mock service. There is deliberately no live URL/selector override.
    from urllib.parse import urlsplit
    parsed=urlsplit(cfg.mock_merchant_url)
    if parsed.scheme!='http' or parsed.hostname not in ('127.0.0.1','localhost','mock-merchant') or parsed.username or parsed.password:raise RuntimeError('Mock destination rejected')
    base=cfg.mock_merchant_url.rstrip('/')
    with SessionLocal() as db:
        j,m=load_owned(db,jid,token);reference=m.reference;scenario=j.scenario
        nik=decrypt(j.nik_encrypted) if j.nik_encrypted else ''
    with sync_playwright() as p:
        args={'headless':True,'chromium_sandbox':cfg.chromium_sandbox}
        if cfg.browser_executable:args['executable_path']=cfg.browser_executable
        browser=p.chromium.launch(**args)
        try:
            # A fresh context per job: no shared cookies/storage between merchants.
            context=browser.new_context(service_workers='block',accept_downloads=False)
            context.route('**/*',lambda route:route.continue_() if route.request.url.startswith(base+'/') else route.abort())
            page=context.new_page();page.set_default_timeout(15000)
            page.goto(base+'/login');page.locator('#merchant').fill(reference);page.locator('#login').click();page.wait_for_url(base+'/portal')
            identity=page.request.get(base+'/identity').json()
            if identity.get('merchant')!=reference:raise RuntimeError('Context isolation failed')
            if nik:page.locator('#nik').fill(nik)
            if scenario=='retryable_error':raise RuntimeError('Synthetic pre-submit failure')
            if scenario=='verification':
                with SessionLocal() as db:
                    j,m=load_owned(db,jid,token);j.status='WAITING_VERIFICATION';j.phase='verification';j.updated_at=time.time()
                    v=Verification(tenant_id=j.tenant_id,job_id=j.id,expires_at=time.time()+cfg.verification_seconds);db.add(v)
                    db.add(Audit(tenant_id=j.tenant_id,action='verification.waiting',target=str(j.id)));db.commit();vid=v.id
                verified=False
                while not lost.is_set() and not STOP.is_set():
                    with SessionLocal() as db:
                        j,m=load_owned(db,jid,token);v=db.get(Verification,vid)
                        if time.time()>v.expires_at:raise RuntimeError('Verification expired')
                        if v.status=='responded' and v.response_encrypted:
                            code=decrypt(v.response_encrypted);v.response_encrypted=None;db.commit()
                            page.locator('#otp').fill(code);page.locator('#verify').click();code=''
                            verified=page.locator('#status').inner_text()=='verified'
                            v.status='verified' if verified else 'waiting';db.commit()
                            if verified:break
                            if v.attempts>=3:raise RuntimeError('Verification exhausted')
                    time.sleep(.3)
                if not verified:raise RuntimeError('Verification stopped')
            if lost.is_set() or STOP.is_set():raise RuntimeError('Worker stopped')
            with SessionLocal() as db:
                j,m=load_owned(db,jid,token)
                b=db.get(Batch,j.batch_id) if j.batch_id else None
                if b and b.status=='paused':
                    j.status='queued';j.phase='preparing';j.updated_at=time.time();db.commit();return
                # Commit intent BEFORE request; never resubmit an unknown outcome.
                j.phase='submitting';j.status='running';j.updated_at=time.time();key=j.submission_key or f'legacy-{j.id}';kind=j.kind;quantity=j.quantity;db.commit()
            if kind=='transaction':
                response=page.request.post(base+'/submit',data={'key':key})
                if not response.ok:raise RuntimeError('Submission failed')
                if scenario=='crash_after_submit':raise RuntimeError('Synthetic transport loss after submit')
            with SessionLocal() as db:
                j,m=load_owned(db,jid,token)
                if kind=='stock':m.stock=100;m.stock_simulated=True;m.stock_at=time.time()
                elif j.batch_id is None:
                    if m.stock is None or not m.stock_simulated or m.stock<quantity:raise RuntimeError('Insufficient simulation stock')
                    m.stock-=quantity
                j.status='succeeded';j.phase='completed';j.result='SIMULASI: diproses layanan merchant mock; bukan transaksi nyata';j.nik_encrypted=None;j.updated_at=time.time()
                db.add(Audit(tenant_id=j.tenant_id,action='job.succeeded',target=str(j.id)));db.commit()
        finally:
            nik='';browser.close()

def main():
    cfg=settings();root=os.getenv('WORKER_ID',socket.gethostname())
    signal.signal(signal.SIGTERM,lambda *_:STOP.set());signal.signal(signal.SIGINT,lambda *_:STOP.set())
    futures=set()
    with ThreadPoolExecutor(max_workers=cfg.worker_concurrency) as pool:
        while not STOP.is_set():
            try:
                recover();dispatch()
                from pathlib import Path
                Path('/tmp/mapauto-worker-heartbeat').touch()
                # Heartbeat per tenant is not shared with API consumers in other tenants.
                with SessionLocal() as db:
                    for w in db.scalars(select(Worker).where(Worker.id.startswith(root+':'))):w.heartbeat=time.time()
                    db.commit()
                futures={f for f in futures if not f.done()}
                if len(futures)<cfg.worker_concurrency:
                    message=connection().blpop('mapauto:ready',timeout=1)
                    if message and message[1].isdigit():futures.add(pool.submit(run_job,int(message[1]),root))
                else:STOP.wait(.2)
            except Exception:STOP.wait(1)  # Fail closed on Redis/DB outage; no secret-bearing tracebacks.

if __name__=='__main__':main()
