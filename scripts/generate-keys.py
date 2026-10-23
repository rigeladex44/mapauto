"""Create a NEW local environment file without printing secrets or overwriting files."""
import os,secrets
from pathlib import Path
from cryptography.fernet import Fernet
root=Path(__file__).resolve().parents[1]
path=root/'.env'
text=(root/'.env.example').read_text()
values={'POSTGRES_PASSWORD':secrets.token_hex(32),'REDIS_PASSWORD':secrets.token_hex(32),'DATA_ENCRYPTION_KEY':Fernet.generate_key().decode(),'NIK_HASH_KEY':secrets.token_hex(32)}
values['DATABASE_URL']=f"postgresql+psycopg://mapauto:{values['POSTGRES_PASSWORD']}@db:5432/mapauto"
values['REDIS_URL']=f"redis://:{values['REDIS_PASSWORD']}@redis:6379/0"
for name,value in values.items():
    import re
    text=re.sub(r'^'+name+r'=.*$',lambda _:name+'='+value,text,flags=re.M)
fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(fd,'w') as file:file.write(text)
print('Created .env mode 0600. Edit domain/contact settings securely; values not printed.')
