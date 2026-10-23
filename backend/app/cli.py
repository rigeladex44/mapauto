import argparse, getpass, time
from sqlalchemy import select
from .db import SessionLocal
from .models import User, Merchant, Audit
from .security import hash_password
from .config import settings

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('command',choices=['create-admin','seed-demo'])
    args=parser.parse_args()
    with SessionLocal() as db:
        if args.command=='create-admin':
            username=input('Username admin: ').strip().lower()
            import re
            if not re.fullmatch(r'[a-z0-9_.-]{3,80}',username): parser.error('Username tidak valid')
            password=getpass.getpass('Password baru (minimum 12 karakter): ')
            if len(password)<12 or len(password)>128: parser.error('Password harus 12..128 karakter')
            if password!=getpass.getpass('Ulangi password: '): parser.error('Password tidak cocok')
            if db.scalar(select(User).where(User.username==username)): parser.error('Username sudah ada')
            db.add(User(username=username,password_hash=hash_password(password),role='admin'))
            db.add(Audit(action='admin.bootstrap',target='account'))
        else:
            if not settings().demo_mode: parser.error('Set DEMO_MODE=true explicitly first')
            if not db.scalar(select(Merchant).where(Merchant.reference=='demo-001')):
                db.add(Merchant(name='Merchant Demo 01',reference='demo-001',authorized=True))
                db.add(Audit(action='demo.seeded',target='synthetic metadata'))
        db.commit()
    print('Selesai; tidak ada credential ditampilkan.')
if __name__=='__main__': main()
