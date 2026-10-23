import hashlib, hmac
from cryptography.fernet import Fernet, InvalidToken
from .config import settings

def cipher():
    key=settings().data_encryption_key
    if not key: raise ValueError('DATA_ENCRYPTION_KEY belum dikonfigurasi')
    return Fernet(key.encode())
def encrypt(value): return cipher().encrypt(value.encode()).decode()
def decrypt(value): return cipher().decrypt(value.encode()).decode()
def digest(value):
    key=settings().nik_hash_key
    if len(key)<32: raise ValueError('NIK_HASH_KEY belum dikonfigurasi')
    return hmac.new(key.encode(),value.encode(),hashlib.sha256).hexdigest()
def mask(value): return '*'*12+value[-4:]
