import hashlib, secrets, time
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session as DB
from .db import get_db
from .models import User, Session, Tenant, MerchantGrant
from sqlalchemy import select

def hash_password(password):
    salt=secrets.token_hex(16)
    digest=hashlib.scrypt(password.encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1).hex()
    return f'scrypt${salt}${digest}'

def verify_password(password, stored):
    try:
        _, salt, expected=stored.split('$')
        actual=hashlib.scrypt(password.encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1).hex()
        return secrets.compare_digest(actual,expected)
    except (ValueError,TypeError): return False

def token_hash(token): return hashlib.sha256(token.encode()).hexdigest()

def current_user(request: Request, db: DB = Depends(get_db)):
    token=request.cookies.get('mapauto_session','')
    session=db.get(Session,token_hash(token)) if token else None
    user=db.get(User,session.user_id) if session else None
    now=time.time()
    if not session or session.expires_at<=now or not user or not user.active or (user.expires_at is not None and user.expires_at<=now):
        raise HTTPException(401,'Sesi tidak aktif atau masa aktif berakhir')
    if request.method not in ('GET','HEAD','OPTIONS') and not secrets.compare_digest(request.headers.get('X-CSRF-Token',''),session.csrf):
        raise HTTPException(403,'CSRF token diperlukan')
    tenant=db.get(Tenant,user.tenant_id)
    if not tenant or not tenant.active: raise HTTPException(403,"Tenant nonaktif")
    db.info["tenant_id"]=user.tenant_id
    if user.role!='admin':
        db.info['merchant_ids']=list(db.scalars(select(MerchantGrant.merchant_id).where(MerchantGrant.user_id==user.id)))
    request.state.session=session
    return user

def require(*roles):
    def dependency(user: User = Depends(current_user)):
        if user.role not in roles: raise HTTPException(403,'Akses tidak diizinkan')
        return user
    return dependency
