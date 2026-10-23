import time
from sqlalchemy import select
from backend.app.config import Settings, settings
from backend.app.db import SessionLocal
from backend.app.models import User, Session, Job, Merchant, Notification, SystemSetting
from backend.app.domain import extend_expiry, validate_filters, AuthorizedMerchantAdapter
from backend.app.worker import tick, notify
from backend.tests.conftest import signin
import pytest

MERCHANT={'name':'Synthetic Merchant','reference':'test-001','authorized':True,'active':True,'filters':['RUMAH TANGGA']}
def merchant(client):
    r=client.post('/api/merchants',json=MERCHANT);assert r.status_code==201;return r.json()['id']
def queue(client,mid,kind='stock',**extra):
    r=client.post('/api/jobs',json={'merchant_id':mid,'kind':kind,**extra});assert r.status_code==201;return r.json()['id']
def finish(worker='test-worker'):
    tick(worker)
    with SessionLocal() as db:
        for j in db.scalars(select(Job).where(Job.status=='running')): j.updated_at=time.time()-3
        db.commit()
    tick(worker)

def test_auth_csrf_and_session_revocation(client):
    assert client.get('/api/merchants').status_code==401
    signin(client)
    assert client.cookies.get('mapauto_session')
    assert 'httponly' in client.post('/api/auth/login',json={'username':'admin','password':'test-password-only'}).headers['set-cookie'].lower()
    signin(client)
    token=client.headers.pop('X-CSRF-Token')
    assert client.post('/api/merchants',json=MERCHANT).status_code==403
    client.headers['X-CSRF-Token']=token
    assert client.post('/api/auth/logout').status_code==204
    assert client.get('/api/auth/me').status_code==401

def test_viewer_rbac(client):
    signin(client,'viewer')
    for path,method,body in [('/users','GET',None),('/logs','GET',None),('/settings','GET',None),('/merchants','POST',MERCHANT),('/jobs','POST',{'merchant_id':1,'kind':'stock'}),('/reports/jobs.csv','GET',None)]:
        assert client.request(method,'/api'+path,json=body).status_code==403
    assert client.get('/api/dashboard').status_code==200

def test_operator_rbac(client):
    signin(client,'operator');merchant(client)
    assert client.get('/api/users').status_code==403
    assert client.put('/api/settings',json={'telegram_notifications':False}).status_code==403

def test_demo_worker_stock_transaction_report(client):
    signin(client);mid=merchant(client)
    stock=queue(client,mid);finish()
    assert client.get('/api/merchants').json()[0]['stock']==100
    assert client.get('/api/merchants').json()[0]['stock_simulated'] is True
    queue(client,mid,'transaction',quantity=3);finish()
    assert client.get('/api/merchants').json()[0]['stock']==97
    jobs=client.get('/api/jobs').json();assert all(j['status']=='succeeded' and j['simulated'] for j in jobs)
    assert all('SIMULASI' in j['result'] for j in jobs)
    report=client.get('/api/reports/jobs.csv');assert report.status_code==200 and 'True' in report.text
    assert report.headers['cache-control']=='no-store'
    assert client.get('/api/logs').json()

def test_fail_closed_live_and_demo_off(client):
    signin(client);mid=merchant(client)
    assert client.post('/api/jobs',json={'merchant_id':mid,'kind':'transaction','simulated':False}).status_code==409
    cfg=settings();cfg.demo_mode=False
    try: assert client.post('/api/jobs',json={'merchant_id':mid,'kind':'stock'}).status_code==409
    finally: cfg.demo_mode=True
    with pytest.raises(ValueError): AuthorizedMerchantAdapter().execute()

def test_worker_pause_cancel_and_failed_transaction(client):
    signin(client);mid=merchant(client);tick('w')
    client.put('/api/workers/w',json={'paused':True})
    jid=queue(client,mid);tick('w')
    assert client.get('/api/jobs').json()[0]['status']=='queued'
    assert client.post(f'/api/jobs/{jid}/cancel').status_code==200
    assert client.post(f'/api/jobs/{jid}/cancel').status_code==409
    client.put('/api/workers/w',json={'paused':False})
    queue(client,mid,'transaction');finish('w')
    assert client.get('/api/jobs').json()[0]['status']=='failed'

def test_authorization_filter_and_duplicate_validation(client):
    signin(client);mid=merchant(client)
    assert client.post('/api/merchants',json=MERCHANT).status_code==409
    bad={**MERCHANT,'reference':'new-ref','filters':['OTHER']}
    assert client.post('/api/merchants',json=bad).status_code==422
    queue(client,mid)
    assert client.put(f'/api/merchants/{mid}',json={**MERCHANT,'authorized':False}).status_code==200
    assert client.get('/api/jobs').json()[0]['status']=='cancelled'
    assert client.post('/api/jobs',json={'merchant_id':mid,'kind':'stock'}).status_code==400

def test_user_expiry_disable_and_password(client):
    signin(client)
    u=client.post('/api/users',json={'username':'new-user','password':'long-test-pass','role':'operator'}).json()
    assert u['expires_at']>time.time()
    r=client.put('/api/users/'+str(u['id']),json={'active':True,'role':'viewer','extend_days':5})
    assert r.status_code==200 and r.json()['expires_at']>u['expires_at']+4*86400
    assert 'password_hash' not in str(client.get('/api/users').json())
    assert client.put('/api/users/1',json={'active':False,'role':'admin','extend_days':0}).status_code==400
    assert client.post('/api/auth/password',json={'current_password':'test-password-only','new_password':'new-test-password'}).status_code==204
    assert client.get('/api/auth/me').status_code==401
    assert client.post('/api/auth/login',json={'username':'admin','password':'new-test-password'}).status_code==200

def test_expired_and_throttle(client):
    for _ in range(5): assert client.post('/api/auth/login',json={'username':'viewer','password':'wrong'}).status_code==401
    assert client.post('/api/auth/login',json={'username':'viewer','password':'test-password-only'}).status_code==429
    with SessionLocal() as db:
        u=db.scalar(select(User).where(User.username=='operator'));u.expires_at=time.time()-1;db.commit()
    assert client.post('/api/auth/login',json={'username':'operator','password':'test-password-only'}).status_code==401

def test_no_secret_echo_headers_or_config(client):
    secret='DO-NOT-ECHO'*20
    r=client.post('/api/auth/login',json={'username':'admin','password':secret})
    assert r.status_code==422 and secret not in r.text
    signin(client)
    r=client.get('/api/settings');assert r.headers['cache-control']=='no-store'
    assert r.headers['x-frame-options']=='DENY'
    assert 'telegram_bot_token' not in r.text
    assert client.put('/api/settings',json={'telegram_notifications':True}).status_code==409
    assert client.get('/api/health',headers={'host':'evil.example'}).status_code==400

def test_expiry_rule_and_production_guards():
    assert extend_expiry(200,100,1)==86600
    assert extend_expiry(50,100,1)==86500
    with pytest.raises(ValueError): validate_filters([])
    with pytest.raises(ValueError): Settings(app_env='production',database_url='sqlite:///a',cookie_secure=True,demo_mode=False).validate_runtime()

def test_worker_rechecks_creator_and_stale_jobs(client):
    signin(client);mid=merchant(client);queue(client,mid);tick('w')
    with SessionLocal() as db:
        u=db.get(User,1);u.active=False
        for j in db.scalars(select(Job)):j.updated_at=time.time()-5
        db.commit()
    tick('w')
    with SessionLocal() as db: assert db.scalar(select(Job)).status=='failed'

def test_notification_off_makes_no_network(client,monkeypatch):
    signin(client);mid=merchant(client);jid=queue(client,mid)
    with SessionLocal() as db:
        db.add(Notification(job_id=jid));db.commit()
    import httpx
    monkeypatch.setattr(httpx.Client,'post',lambda *a,**kw:pytest.fail('No outbound notification allowed'))
    notify()
    with SessionLocal() as db:assert db.scalar(select(Notification)).status=='pending'

def test_login_csrf_and_session_expiry(client):
    assert client.post('/api/auth/login',headers={'Origin':'https://evil.example'},json={'username':'admin','password':'test-password-only'}).status_code==403
    signin(client)
    with SessionLocal() as db:
        for s in db.scalars(select(Session)):s.expires_at=time.time()-1
        db.commit()
    assert client.get('/api/auth/me').status_code==401

def test_parallel_workers_serialize_stock_on_postgres(client):
    from backend.app.db import engine
    if engine.dialect.name!='postgresql': pytest.skip('PostgreSQL row-lock concurrency test')
    from concurrent.futures import ThreadPoolExecutor
    from backend.app.models import Worker
    signin(client);mid=merchant(client)
    with SessionLocal() as db:
        m=db.get(Merchant,mid);m.stock=100;m.stock_simulated=True
        for name in ['parallel-a','parallel-b']:
            db.add(Worker(id=name,heartbeat=time.time(),paused=False))
            db.add(Job(merchant_id=mid,created_by=1,kind='transaction',quantity=5,status='running',worker_id=name,updated_at=time.time()-5))
        db.commit()
    with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(tick,['parallel-a','parallel-b']))
    with SessionLocal() as db:
        assert db.get(Merchant,mid).stock==90
        assert all(j.status=='succeeded' for j in db.scalars(select(Job)))

def test_password_not_trimmed_and_non_demo_summary(client):
    signin(client);mid=merchant(client);queue(client,mid);finish()
    r=client.post('/api/users',json={'username':'spaces-user','password':'  long password  ','role':'viewer'})
    assert r.status_code==201
    client.post('/api/auth/logout')
    assert client.post('/api/auth/login',json={'username':'spaces-user','password':'  long password  '}).status_code==200
    signin(client)
    settings().demo_mode=False
    try:assert client.get('/api/dashboard').json()['stock']==0
    finally:settings().demo_mode=True

def test_opted_in_notification_delivery_is_mocked(client,monkeypatch):
    signin(client);mid=merchant(client);jid=queue(client,mid)
    with SessionLocal() as db:
        db.add(Notification(job_id=jid));db.add(SystemSetting(key='notifications',value={'enabled':True}));db.commit()
    cfg=settings();old=(cfg.telegram_enabled,cfg.telegram_bot_token,cfg.telegram_chat_id)
    cfg.telegram_enabled=True;cfg.telegram_bot_token='synthetic-test-token';cfg.telegram_chat_id='synthetic-test-target'
    import httpx
    def mock_post(self,url,**kwargs):
        assert set(kwargs['json'])=={'chat_id','text'}
        assert 'Synthetic Merchant' not in kwargs['json']['text']
        return httpx.Response(200,json={'ok':True})
    monkeypatch.setattr(httpx.Client,'post',mock_post)
    try:
        notify()
        with SessionLocal() as db:assert db.scalar(select(Notification)).status=='sent'
    finally:cfg.telegram_enabled,cfg.telegram_bot_token,cfg.telegram_chat_id=old
