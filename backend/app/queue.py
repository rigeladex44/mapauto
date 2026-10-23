"""Redis is delivery transport; PostgreSQL remains the durable source of truth.
Only numeric job IDs are placed in Redis. Duplicate messages are harmless.
"""
import time
import redis
from sqlalchemy import select
from .config import settings
from .db import SessionLocal
from .models import Job, Batch

def connection(): return redis.Redis.from_url(settings().redis_url,decode_responses=True,socket_timeout=3,socket_connect_timeout=3)
def dispatch():
    r=connection()
    with SessionLocal() as db:
        candidates=db.scalars(select(Job).where(Job.status=='queued').order_by(Job.id).limit(100)).all()
        for j in candidates:
            batch=db.get(Batch,j.batch_id) if j.batch_id else None
            if batch and batch.status!='queued': continue
            # Delivery latch expires if a popped message is lost before claiming.
            if r.set(f'mapauto:delivered:{j.id}', '1', nx=True, ex=10):
                r.rpush('mapauto:ready',str(j.id))
        # Bound duplicate transport storage; DB dispatcher can regenerate it.
        r.ltrim('mapauto:ready',-2000,-1)
    return len(candidates)
