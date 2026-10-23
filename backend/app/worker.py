"""Durable simulation worker. Never imports legacy browser/Telegram handlers."""
import os, signal, socket, time
import httpx
from sqlalchemy import select, update
from .config import settings
from .db import SessionLocal
from .models import Job, Worker, Merchant, Audit, SystemSetting, Notification, User

stopping=False

def tick(worker_id):
    now=time.time()
    with SessionLocal() as db:
        w=db.get(Worker,worker_id)
        if not w:
            w=Worker(id=worker_id,heartbeat=now,paused=False); db.add(w)
        else: w.heartbeat=now
        # Do not silently replay a transaction after losing a worker.
        for j in db.scalars(select(Job).where(Job.status=='running',Job.batch_id.is_(None))):
            previous=db.get(Worker,j.worker_id) if j.worker_id else None
            if not previous or now-previous.heartbeat>60:
                j.status='failed'; j.result='Worker terputus; tinjau sebelum menjadwalkan ulang'; j.updated_at=now
        db.commit()
        # Finish only work owned by this worker; lock against cancellation.
        for j in db.scalars(select(Job).where(Job.status=='running',Job.worker_id==worker_id,Job.batch_id.is_(None)).with_for_update()):
            if now-j.updated_at<2: continue
            merchant=db.scalar(select(Merchant).where(Merchant.id==j.merchant_id).with_for_update())
            creator=db.get(User,j.created_by)
            if not creator or not creator.active or creator.role not in ('admin','operator') or (creator.expires_at is not None and creator.expires_at<=now):
                j.status='failed'; j.result='Hak akses pembuat job berakhir'
            elif not settings().demo_mode or not j.simulated:
                j.status='failed'; j.result='Live integration disabled'
            elif not merchant or not merchant.active or not merchant.authorized:
                j.status='cancelled'; j.result='Merchant tidak diotorisasi'
            elif j.kind=='stock':
                merchant.stock=100; merchant.stock_at=now; merchant.stock_simulated=True
                j.status='succeeded'; j.result='SIMULASI: stok 100 tabung; tidak ada permintaan eksternal'
            elif merchant.stock is None or not merchant.stock_simulated or merchant.stock<j.quantity:
                j.status='failed'; j.result='SIMULASI: stok tidak cukup; lakukan pemeriksaan stok simulasi'
            else:
                merchant.stock-=j.quantity; merchant.stock_at=now
                j.status='succeeded'; j.result='SIMULASI: pencatatan lokal; bukan transaksi merchant'
            j.updated_at=now
            db.add(Audit(tenant_id=j.tenant_id,actor_id=None,action='job.'+j.status,target=str(j.id)))
            s=db.get(SystemSetting,(j.tenant_id,'notifications'))
            if s and s.value.get('enabled'): db.add(Notification(job_id=j.id,tenant_id=j.tenant_id))
        db.commit()
        if w.paused: return
        # Conditional UPDATE works on SQLite and PostgreSQL; only one claimant wins.
        candidate=db.scalar(select(Job.id).where(Job.status=='queued',Job.batch_id.is_(None)).order_by(Job.id).limit(1))
        if candidate is not None:
            db.execute(update(Job).where(Job.id==candidate,Job.status=='queued').values(status='running',worker_id=worker_id,updated_at=now))
            db.commit()

def notify():
    cfg=settings()
    if not (cfg.telegram_enabled and cfg.telegram_bot_token and cfg.telegram_chat_id): return
    with SessionLocal() as db:
        n=db.scalar(select(Notification).where(Notification.status=='pending').with_for_update(skip_locked=True).limit(1))
        if not n: return
        s=db.get(SystemSetting,(n.tenant_id,'notifications'))
        if not s or not s.value.get('enabled'): return
        n.status='sending'; db.commit()
        # At-most-once notification attempt: a crash may require manual review.
        try:
            with httpx.Client(timeout=10,verify=True) as client:
                response=client.post(f'https://api.telegram.org/bot{cfg.telegram_bot_token}/sendMessage',json={'chat_id':cfg.telegram_chat_id,'text':f'Mapauto: job #{n.job_id} selesai. Lihat dashboard untuk status.'})
                n.status='sent' if response.is_success and response.json().get('ok') else 'failed'
        except Exception:
            n.status='failed'  # Never log URL, token, response or personal data.
        db.commit()

def main():
    worker_id=os.getenv('WORKER_ID',socket.gethostname())
    def stop(*_):
        global stopping
        stopping=True
    signal.signal(signal.SIGTERM,stop); signal.signal(signal.SIGINT,stop)
    while not stopping:
        tick(worker_id); notify(); time.sleep(1)
    with SessionLocal() as db:
        w=db.get(Worker,worker_id)
        if w: w.heartbeat=0; db.commit()

if __name__=='__main__': main()
