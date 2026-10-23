import json,os,time,threading,subprocess,sys
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import select,delete
from fastapi.testclient import TestClient
from backend.tests.conftest import signin
from backend.app.main import app
from backend.app.db import SessionLocal
from backend.app.models import Tenant,User,Merchant,Job,Batch,Audit,Verification,MerchantGrant,Worker
from backend.app.security import hash_password
from backend.app.config import settings

SYNTHETIC='0000000000000001'
SECOND='0000000000000002'

def make_merchant(client,reference='vps-001'):
    response=client.post('/api/merchants',json={'name':'Synthetic merchant','reference':reference,'authorized':True,'active':True})
    assert response.status_code==201
    return response.json()['id']
def preview(client,mid,**extra):
    response=client.post('/api/batches/preview',json={'merchant_id':mid,'niks':SYNTHETIC,'idempotency_key':'synthetic-test-request-001',**extra})
    assert response.status_code==201,response.json()
    return response.json()

def test_tenant_and_merchant_boundaries(client):
    signin(client);mid=make_merchant(client)
    batch=preview(client,mid)
    with SessionLocal() as db:
        db.add(Tenant(id=2,name='Second synthetic tenant'));db.flush()
        db.add(User(tenant_id=2,username='other-admin',password_hash=hash_password('test-password-only'),role='admin'));db.commit()
    other=TestClient(app);signin(other,'other-admin')
    assert other.get('/api/merchants').json()==[]
    assert other.get('/api/jobs').json()==[]
    assert other.get('/api/batches').json()==[]
    assert other.get('/api/logs').json()==[]
    assert other.get('/api/users').json()[0]['username']=='other-admin'
    assert other.post(f'/api/batches/{batch["id"]}/confirm').status_code==404
    assert other.put(f'/api/merchants/{mid}',json={'name':'Injected','reference':'attack','authorized':True}).status_code==404
    assert other.post('/api/jobs',json={'merchant_id':mid,'kind':'stock'}).status_code==400
    assert other.put('/api/users/1/merchant-access',json={'merchant_ids':[mid]}).status_code==404
    assert other.get('/api/reports/jobs.csv').text.count('\n')==1

def test_same_tenant_grants_and_operator_restriction(client):
    signin(client);mid=make_merchant(client)
    operator=TestClient(app);signin(operator,'operator')
    assert operator.get('/api/merchants').json()==[]
    assert operator.post('/api/jobs',json={'merchant_id':mid,'kind':'stock'}).status_code==400
    assert client.put('/api/users/2/merchant-access',json={'merchant_ids':[mid]}).status_code==200
    assert len(operator.get('/api/merchants').json())==1
    assert operator.post('/api/jobs',json={'merchant_id':mid,'kind':'stock'}).status_code==201
    assert operator.put(f'/api/merchants/{mid}',json={'name':'Synthetic merchant','reference':'vps-001','authorized':True,'active':False}).status_code==403
    assert client.put('/api/users/2/merchant-access',json={'merchant_ids':[]}).status_code==200
    assert operator.get('/api/jobs').json()==[]

def test_preview_validation_encryption_and_idempotency(client):
    signin(client);mid=make_merchant(client)
    bad=client.post('/api/batches/preview',json={'merchant_id':mid,'niks':'not-a-nik','idempotency_key':'validation-only-001'})
    assert bad.status_code==422 and 'not-a-nik' not in bad.text
    b=preview(client,mid,niks=SYNTHETIC+'\n'+SYNTHETIC+'\n'+SECOND)
    assert b['total']==2 and b['duplicates_removed']==1
    assert SYNTHETIC not in json.dumps(b) and SECOND not in json.dumps(b)
    same=preview(client,mid,niks=SYNTHETIC+'\n'+SYNTHETIC+'\n'+SECOND)
    assert same['id']==b['id']
    mismatch=client.post('/api/batches/preview',json={'merchant_id':mid,'niks':SECOND,'idempotency_key':'synthetic-test-request-001'})
    assert mismatch.status_code==409
    with SessionLocal() as db:
        rows=db.scalars(select(Job)).all();assert len(rows)==2
        assert all(SYNTHETIC not in j.nik_encrypted and len(j.nik_digest)==64 for j in rows)
    assert client.post(f'/api/batches/{b["id"]}/confirm').status_code==200
    assert client.post(f'/api/batches/{b["id"]}/confirm').status_code==200
    for action,status in [('pause','paused'),('resume','queued'),('cancel','completed')]:
        r=client.post(f'/api/batches/{b["id"]}/control',json={'action':action});assert r.status_code==200
    with SessionLocal() as db:assert all(j.nik_encrypted is None for j in db.scalars(select(Job)))

def test_expired_preview_and_no_live_batch(client):
    signin(client);mid=make_merchant(client);b=preview(client,mid)
    with SessionLocal() as db:q=db.get(Batch,b['id']);q.expires_at=0;db.commit()
    assert client.post(f'/api/batches/{b["id"]}/confirm').status_code==409
    settings().demo_mode=False
    try:assert client.post('/api/batches/preview',json={'merchant_id':mid,'niks':SYNTHETIC,'idempotency_key':'synthetic-live-denied'}).status_code==409
    finally:settings().demo_mode=True

def test_request_size_limit(client):
    r=client.post('/api/auth/login',content=b'x'*65537,headers={'Content-Type':'application/json'})
    assert r.status_code==413

@pytest.fixture
def redis_mock_server():
    if not os.getenv('TEST_REDIS_URL'):pytest.skip('Requires isolated TEST_REDIS_URL and Chromium')
    from backend.app.queue import connection
    cfg=settings();previous=cfg.redis_url;cfg.redis_url=os.environ['TEST_REDIS_URL']
    r=connection();r.flushdb() # Dedicated disposable test Redis ONLY.
    env={**os.environ,'REDIS_URL':cfg.redis_url}
    server=subprocess.Popen([sys.executable,'-m','uvicorn','backend.app.mock_merchant:app','--host','127.0.0.1','--port','8099','--no-access-log'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    import httpx
    for _ in range(50):
        try:
            if httpx.get('http://127.0.0.1:8099/health').status_code==200:break
        except Exception:pass
        time.sleep(.1)
    else:raise RuntimeError('Mock fixture not ready')
    cfg.browser_executable='/usr/bin/chromium'
    try:yield r
    finally:
        server.terminate();server.wait(timeout=10);r.flushdb();cfg.redis_url=previous

def test_redis_queue_browser_duplicate_prevention(client,redis_mock_server):
    from backend.app.queue import dispatch
    from backend.app.browser_worker import run_job
    signin(client);mid=make_merchant(client);b=preview(client,mid)
    client.post(f'/api/batches/{b["id"]}/confirm')
    assert dispatch()==1
    message=redis_mock_server.lpop('mapauto:ready');assert int(message)==b['items'][0]['id']
    jid=int(message);run_job(jid,'test-browser');run_job(jid,'duplicate')
    with SessionLocal() as db:
        q=db.get(Job,jid);assert q.status=='succeeded' and q.nik_encrypted is None
        assert len(list(redis_mock_server.scan_iter('mapauto:mock:receipt:*')))==1
        assert db.scalar(select(Audit).where(Audit.action=='job.succeeded'))

def test_manual_verification_tenant_and_timeout(client,redis_mock_server):
    from backend.app.browser_worker import run_job
    signin(client);mid=make_merchant(client);b=preview(client,mid,scenario='verification');client.post(f'/api/batches/{b["id"]}/confirm');jid=b['items'][0]['id']
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(run_job,jid,'verify-browser')
        for _ in range(150):
            rows=client.get('/api/verifications').json()
            if rows:break
            time.sleep(.1)
        assert rows
        viewer=TestClient(app);signin(viewer,'viewer')
        assert viewer.get('/api/verifications').json()==[]
        assert viewer.post(f'/api/verifications/{rows[0]["id"]}/respond',json={'code':'246810'}).status_code==403
        assert client.post(f'/api/verifications/{rows[0]["id"]}/respond',json={'code':'246810'}).status_code==200
        future.result(timeout=20)
    with SessionLocal() as db:
        assert db.get(Job,jid).status=='succeeded'
        assert db.scalar(select(Verification)).response_encrypted is None

def test_unknown_submission_never_replayed_and_reconciliation(client,redis_mock_server):
    from backend.app.browser_worker import run_job,recover
    signin(client);mid=make_merchant(client);b=preview(client,mid,scenario='crash_after_submit');client.post(f'/api/batches/{b["id"]}/confirm');jid=b['items'][0]['id']
    run_job(jid,'uncertain-browser')
    with SessionLocal() as db:assert db.get(Job,jid).status=='RECONCILIATION_REQUIRED'
    run_job(jid,'new-browser');recover()
    assert len(list(redis_mock_server.scan_iter('mapauto:mock:receipt:*')))==1
    assert client.post(f'/api/jobs/{jid}/cancel').status_code==409
    assert client.post(f'/api/jobs/{jid}/reconcile',json={'outcome':'confirmed','evidence':'Synthetic receipt checked'}).status_code==200
    assert client.post(f'/api/jobs/{jid}/reconcile',json={'outcome':'confirmed','evidence':'Duplicate reconciliation'}).status_code==409
    with SessionLocal() as db:assert db.get(Job,jid).nik_encrypted is None

def test_worker_restart_recovery_is_phase_sensitive(client,redis_mock_server):
    from backend.app.browser_worker import recover
    signin(client);mid=make_merchant(client)
    ids=[]
    with SessionLocal() as db:
        for phase,status in [('preparing','running'),('submitting','running'),('verification','WAITING_VERIFICATION')]:
            j=Job(tenant_id=1,merchant_id=mid,created_by=1,kind='transaction',status=status,phase=phase,lease_until=0);db.add(j);db.flush();ids.append(j.id)
        db.commit()
    recover()
    with SessionLocal() as db:assert [db.get(Job,j).status for j in ids]==['queued','RECONCILIATION_REQUIRED','failed']

def test_pre_submit_failure_and_paused_queue(client,redis_mock_server):
    from backend.app.browser_worker import run_job
    signin(client);mid=make_merchant(client);b=preview(client,mid,scenario='retryable_error');client.post(f'/api/batches/{b["id"]}/confirm');jid=b['items'][0]['id']
    client.post(f'/api/batches/{b["id"]}/control',json={'action':'pause'});run_job(jid)
    with SessionLocal() as db:assert db.get(Job,jid).status=='queued'
    client.post(f'/api/batches/{b["id"]}/control',json={'action':'resume'});run_job(jid)
    with SessionLocal() as db:assert db.get(Job,jid).status=='failed'
    assert not list(redis_mock_server.scan_iter('mapauto:mock:receipt:*'))
