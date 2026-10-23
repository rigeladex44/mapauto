"""Create a NEW local environment file without printing secrets or overwriting files."""
import argparse, base64, os, secrets
from pathlib import Path
root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--local-demo',action='store_true',help='Create isolated local demo configuration')
args=parser.parse_args()
path=root/('.env.local-demo' if args.local_demo else '.env')
text=(root/'.env.example').read_text()
values={'POSTGRES_PASSWORD':secrets.token_hex(32),'REDIS_PASSWORD':secrets.token_hex(32),'DATA_ENCRYPTION_KEY':base64.urlsafe_b64encode(os.urandom(32)).decode(),'NIK_HASH_KEY':secrets.token_hex(32)}
values['DATABASE_URL']=f"postgresql+psycopg://mapauto:{values['POSTGRES_PASSWORD']}@db:5432/mapauto"
values['REDIS_URL']=f"redis://:{values['REDIS_PASSWORD']}@redis:6379/0"
if args.local_demo: values.update(APP_ENV='development',DEMO_MODE='true',ALLOWED_HOSTS='localhost,127.0.0.1',COOKIE_SECURE='false')
for name,value in values.items():
    import re
    text=re.sub(r'^'+name+r'=.*$',lambda _:name+'='+value,text,flags=re.M)
fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(fd,'w') as file:file.write(text)
print(f'Created {path.name} mode 0600. Secret values were not printed.')
