import asyncio
import tempfile
import time
import unittest
from pathlib import Path
from fastapi.testclient import TestClient
from portal.backend.app import create_app

KEY='test-key-'+'a'*32
class FakeMerchant:
    heading=False
    def __init__(self): self.stock_value=146
    async def login(self, identity, pin): pass
    async def dashboard(self): return {'name':'TEST PANGKALAN','subname':'TEST'}
    async def stock(self):
        if self.stock_value is None: raise ValueError('unreadable')
        return self.stock_value
    async def prepare(self, nik, mode, emit):
        await emit('Memeriksa pelanggan'); await asyncio.sleep(.15)
        return {'status':'Siap ditinjau','type':'UM','reason':'Belum transaksi.'}
    async def close(self): pass

class ApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.adapters=[]
        def factory():
            m=FakeMerchant();self.adapters.append(m);return m
        self.client=TestClient(create_app(factory,Path(self.tmp.name)/'db.sqlite',KEY));self.client.__enter__()
    def tearDown(self): self.client.__exit__(None,None,None);self.tmp.cleanup()
    def login(self, identity='tester@example.invalid'):
        r=self.client.post('/api/login',json={'access_key':KEY,'identity':identity,'pin':'123456'})
        self.assertEqual(r.status_code,202);headers={'Authorization':'Bearer '+r.json()['session_token']}
        for _ in range(50):
            if self.client.get('/api/session',headers=headers).json()['state']=='Terhubung': break
            time.sleep(.01)
        return headers
    def wait_done(self,headers,bid):
        for _ in range(100):
            data=self.client.get('/api/batches/'+bid,headers=headers).json()
            if data['state'] not in ['Berjalan','Dijeda','Menghentikan']: return data
            time.sleep(.02)
        self.fail('worker did not finish')
    def test_auth_isolation_and_one_session_per_account(self):
        self.assertEqual(self.client.get('/api/session').status_code,401)
        h=self.login();other=self.login('other@example.invalid')
        r=self.client.post('/api/login',json={'access_key':KEY,'identity':'tester@example.invalid','pin':'123456'})
        self.assertEqual(r.status_code,409)
        data=self.client.post('/api/batches',headers=h,json={'niks':['0'*15+'1'],'mode':'RT & UM'}).json()
        self.assertEqual(self.client.get('/api/batches/'+data['id'],headers=other).status_code,404)
        done=self.wait_done(h,data['id']);self.assertEqual(done['rows'][0]['status'],'Siap ditinjau')
        self.assertEqual(done['rows'][0]['qty'],0)
    def test_pause_stop_serialization_and_preserve_unprocessed(self):
        h=self.login();payload={'niks':['0'*15+'1','0'*15+'2'],'mode':'RT & UM'}
        data=self.client.post('/api/batches',headers=h,json=payload).json();bid=data['id']
        self.assertEqual(self.client.post('/api/batches',headers=h,json=payload).status_code,409)
        self.assertEqual(self.client.post('/api/stock/sync',headers=h,json={}).status_code,409)
        self.assertEqual(self.client.post('/api/logout',headers=h,json={}).status_code,409)
        self.client.post('/api/batches/'+bid+'/control',headers=h,json={'action':'pause'})
        time.sleep(.3)
        paused=self.client.get('/api/batches/'+bid,headers=h).json()
        self.assertEqual(paused['rows'][1]['status'],'Menunggu')
        self.client.post('/api/batches/'+bid+'/control',headers=h,json={'action':'stop'})
        done=self.wait_done(h,bid);self.assertEqual(done['state'],'Dihentikan')
        self.assertEqual(done['rows'][1]['status'],'Menunggu')
    def test_failed_stock_keeps_last_value_and_timestamp(self):
        h=self.login();before=self.client.get('/api/session',headers=h).json();self.adapters[0].stock_value=None
        after=self.client.post('/api/stock/sync',headers=h,json={}).json()
        self.assertEqual(after['stock'],146);self.assertEqual(after['last_sync'],before['last_sync'])
        self.assertIn('belum tersinkron',after['message'])
    def test_input_and_origin_validation(self):
        h=self.login()
        self.assertEqual(self.client.post('/api/batches',headers=h,json={'niks':['123'],'mode':'RT'}).status_code,422)
        self.assertEqual(self.client.post('/api/login',headers={'Origin':'https://evil.example'},json={}).status_code,403)
        self.assertEqual(self.client.post('/api/login',json={'identity':'secret'}).json(),{'detail':'Format permintaan tidak valid.'})
