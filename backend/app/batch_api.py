import hashlib, json, re, time
from collections import Counter
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session as DB
from .schemas import Strict
from .security import current_user, require
from .db import get_db
from .models import Batch, Job, Merchant, Audit, Verification, User, MerchantGrant
from .config import settings
from .crypto import encrypt, digest, mask

router=APIRouter(prefix='/api')
class Preview(Strict):
    merchant_id: int
    niks: str = Field(min_length=1,max_length=24000)
    idempotency_key: str = Field(min_length=16,max_length=64,pattern=r'^[a-zA-Z0-9_-]+$')
    scenario: Literal['normal','verification','retryable_error','crash_after_submit']='normal'
class Control(Strict):
    action: Literal['pause','resume','cancel']
class VerificationInput(Strict):
    code: str = Field(min_length=1,max_length=64)
class Reconcile(Strict):
    outcome: Literal['confirmed','not_submitted']
    evidence: str = Field(min_length=8,max_length=500)

def audit(db,user,action,target):db.add(Audit(tenant_id=user.tenant_id,actor_id=user.id,action=action,target=str(target)))
def get_batch(db,bid):
    b=db.scalar(select(Batch).where(Batch.id==bid).with_for_update())
    if not b:raise HTTPException(404,'Batch tidak ditemukan')
    return b

def info(db,b):
    jobs=db.scalars(select(Job).where(Job.batch_id==b.id).order_by(Job.id)).all()
    counts=dict(Counter(j.status for j in jobs))
    terminal={'succeeded','failed','cancelled'}
    effective='completed' if jobs and all(j.status in terminal for j in jobs) else b.status
    return dict(id=b.id,merchant_id=b.merchant_id,status=effective,expires_at=b.expires_at,created_at=b.created_at,total=len(jobs),counts=counts,
        items=[dict(id=j.id,nik=j.nik_masked,status=j.status,result=j.result,phase=j.phase) for j in jobs])

@router.post('/batches/preview',status_code=201)
def preview(data:Preview,user=Depends(require('admin','operator')),db:DB=Depends(get_db)):
    if not settings().demo_mode:raise HTTPException(409,'Batch live ditutup sampai adapter resmi diotorisasi. Gunakan data sintetis di Demo Mode')
    m=db.get(Merchant,data.merchant_id)
    if not m or not m.active or not m.authorized:raise HTTPException(404,'Merchant aktif berotorisasi tidak ditemukan')
    lines=[v.strip() for v in re.split(r'[\s,;]+',data.niks) if v.strip()]
    if len(lines)>1000:raise HTTPException(422,'Maksimal 1000 baris per batch')
    invalid=[i+1 for i,v in enumerate(lines) if not re.fullmatch(r'[0-9]{16}',v)]
    if invalid:raise HTTPException(422,f'Format NIK salah pada posisi: {", ".join(map(str,invalid[:20]))}; harus 16 digit. Nilai tidak ditampilkan')
    unique=list(dict.fromkeys(lines));request_digest=digest(json.dumps([m.id,unique,data.scenario]))
    key=digest(f'{user.tenant_id}:{data.idempotency_key}')
    existing=db.scalar(select(Batch).where(Batch.idempotency_key==key))
    if existing:
        if existing.request_digest!=request_digest:raise HTTPException(409,'Idempotency key sudah dipakai untuk payload berbeda')
        result=info(db,existing);result['duplicates_removed']=len(lines)-len(unique);return result
    # Resolve crypto configuration before writing any rows.
    encrypted=[encrypt(v) for v in unique]
    b=Batch(merchant_id=m.id,created_by=user.id,idempotency_key=key,request_digest=request_digest)
    db.add(b);db.flush()
    for value,ciphertext in zip(unique,encrypted):
        db.add(Job(tenant_id=user.tenant_id,merchant_id=m.id,created_by=user.id,kind='transaction',batch_id=b.id,status='preview',
            nik_encrypted=ciphertext,nik_digest=digest(f'{m.id}:{value}'),nik_masked=mask(value),submission_key=digest(f'{key}:{value}'),scenario=data.scenario))
    audit(db,user,'batch.preview',b.id)
    try:db.commit()
    except Exception:
        db.rollback();raise HTTPException(409,'Konflik batch; ulangi dengan idempotency key yang sama')
    result=info(db,b);result['duplicates_removed']=len(lines)-len(unique);return result

@router.get('/batches')
def batches(user=Depends(current_user),db:DB=Depends(get_db)):
    return [info(db,b) for b in db.scalars(select(Batch).order_by(Batch.id.desc()).limit(50))]

@router.post('/batches/{bid}/confirm')
def confirm(bid:int,user=Depends(require('admin','operator')),db:DB=Depends(get_db)):
    b=get_batch(db,bid);m=db.get(Merchant,b.merchant_id)
    if not settings().demo_mode or not m or not m.active or not m.authorized:raise HTTPException(409,'Merchant/mode tidak mengizinkan pemrosesan')
    if b.status=='queued':return info(db,b)
    if b.status!='preview' or b.expires_at<time.time():raise HTTPException(409,'Preview kedaluwarsa atau sudah diproses')
    b.status='queued'
    for j in db.scalars(select(Job).where(Job.batch_id==b.id,Job.status=='preview')):j.status='queued';j.updated_at=time.time()
    audit(db,user,'batch.confirmed',b.id);db.commit();return info(db,b)

@router.post('/batches/{bid}/control')
def control(bid:int,data:Control,user=Depends(require('admin','operator')),db:DB=Depends(get_db)):
    b=get_batch(db,bid)
    if data.action=='pause':
        if b.status!='queued':raise HTTPException(409,'Hanya batch antrean yang dapat dijeda')
        b.status='paused'
    elif data.action=='resume':
        if b.status!='paused':raise HTTPException(409,'Batch tidak dijeda')
        b.status='queued'
    else:
        b.status='cancelled'
        for j in db.scalars(select(Job).where(Job.batch_id==b.id,Job.status.in_(['preview','queued','running','WAITING_VERIFICATION'])).with_for_update()):
            j.status='RECONCILIATION_REQUIRED' if j.phase=='submitting' else 'cancelled';j.updated_at=time.time()
            j.result='Permintaan pembatalan; tinjau pengiriman jika status belum diketahui'
            j.nik_encrypted=None if j.status=='cancelled' else j.nik_encrypted
    audit(db,user,'batch.'+data.action,b.id);db.commit();return info(db,b)

@router.get('/verifications')
def verifications(user=Depends(current_user),db:DB=Depends(get_db)):
    return [dict(id=v.id,job_id=v.job_id,status=v.status,expires_at=v.expires_at,attempts=v.attempts) for v in db.scalars(select(Verification).where(Verification.status=='waiting'))]

@router.post('/verifications/{vid}/respond')
def respond(vid:int,data:VerificationInput,user=Depends(require('admin','operator')),db:DB=Depends(get_db)):
    v=db.scalar(select(Verification).where(Verification.id==vid).with_for_update())
    j=db.get(Job,v.job_id) if v else None
    if not v or not j:raise HTTPException(404,'Checkpoint tidak ditemukan')
    if v.status!='waiting' or v.expires_at<time.time() or j.status!='WAITING_VERIFICATION':raise HTTPException(409,'Checkpoint tidak aktif atau kedaluwarsa')
    if v.attempts>=3:raise HTTPException(429,'Batas percobaan tercapai')
    v.response_encrypted=encrypt(data.code);v.status='responded';v.operator_id=user.id;v.attempts+=1
    audit(db,user,'verification.responded',j.id);db.commit();return {'accepted':True}

@router.post('/jobs/{jid}/reconcile')
def reconcile(jid:int,data:Reconcile,user=Depends(require('admin','operator')),db:DB=Depends(get_db)):
    j=db.scalar(select(Job).where(Job.id==jid).with_for_update())
    if not j:raise HTTPException(404,'Job tidak ditemukan')
    if j.status!='RECONCILIATION_REQUIRED':raise HTTPException(409,'Job tidak memerlukan rekonsiliasi')
    j.status='succeeded' if data.outcome=='confirmed' else 'failed';j.phase='reconciled';j.nik_encrypted=None
    j.result='SIMULASI: rekonsiliasi operator '+data.outcome;j.updated_at=time.time()
    audit(db,user,'job.reconciled.'+data.outcome,j.id)
    # Preserve evidence encrypted; never copy untrusted text into audit/log/UI.
    from .models import Reconciliation
    db.add(Reconciliation(tenant_id=user.tenant_id,job_id=j.id,operator_id=user.id,evidence_encrypted=encrypt(data.evidence),outcome=data.outcome))
    db.commit();return {'status':j.status}

class GrantInput(Strict):
    merchant_ids: list[int] = Field(max_length=1000)

@router.put('/users/{uid}/merchant-access')
def grant(uid:int,data:GrantInput,user=Depends(require('admin')),db:DB=Depends(get_db)):
    from sqlalchemy import delete
    u=db.get(User,uid)
    if not u:raise HTTPException(404,'Pengguna tidak ditemukan')
    ids=list(set(data.merchant_ids))
    found=list(db.scalars(select(Merchant.id).where(Merchant.id.in_(ids))))
    if set(found)!=set(ids):raise HTTPException(404,'Merchant tidak ditemukan dalam tenant')
    db.execute(delete(MerchantGrant).where(MerchantGrant.user_id==uid))
    for mid in ids:db.add(MerchantGrant(tenant_id=user.tenant_id,user_id=uid,merchant_id=mid))
    audit(db,user,'merchant.access.updated',uid);db.commit();return {'merchant_ids':ids}
