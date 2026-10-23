import os, tempfile
# An isolated database; no legacy configuration is loaded.
os.environ['DATABASE_URL']=os.environ.get('TEST_DATABASE_URL','sqlite:///'+tempfile.mktemp(suffix='.db'))
os.environ['DEMO_MODE']='true'
from cryptography.fernet import Fernet
os.environ['DATA_ENCRYPTION_KEY']=Fernet.generate_key().decode()
os.environ['NIK_HASH_KEY']='synthetic-test-hash-key-not-for-production'
os.environ['CHROMIUM_SANDBOX']='false'
os.environ['APP_ENV']='development'
os.environ['COOKIE_SECURE']='false'
os.environ['ALLOWED_HOSTS']='localhost,127.0.0.1,testserver'
os.environ['TELEGRAM_ENABLED']='false'
import pytest
from fastapi.testclient import TestClient
from backend.app.db import Base, engine, SessionLocal
from backend.app.models import User, Tenant
from backend.app.security import hash_password
from backend.app.main import app

@pytest.fixture(autouse=True)
def database():
    Base.metadata.drop_all(engine); Base.metadata.create_all(engine)
    with SessionLocal() as db:
        db.add(Tenant(id=1,name='Test tenant'));db.flush()
        for role in ['admin','operator','viewer']:
            db.add(User(username=role,password_hash=hash_password('test-password-only'),role=role))
        db.commit()
    yield

@pytest.fixture
def client():
    with TestClient(app) as client: yield client

def signin(client,role='admin'):
    response=client.post('/api/auth/login',json={'username':role,'password':'test-password-only'})
    assert response.status_code==200
    client.headers['X-CSRF-Token']=response.json()['csrf']
    return response.json()
