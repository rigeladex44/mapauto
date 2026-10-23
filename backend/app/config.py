from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    app_env: str = 'development'
    database_url: str = 'sqlite:///./mapauto.db'
    cookie_secure: bool = False
    allowed_hosts: str = 'localhost,127.0.0.1,testserver'
    demo_mode: bool = False
    redis_url: str = 'redis://localhost:6379/0'
    data_encryption_key: str = ''
    nik_hash_key: str = ''
    max_browser_contexts: int = 1
    chromium_sandbox: bool = True
    rate_limit_enabled: bool = False
    worker_concurrency: int = 1
    worker_lease_seconds: int = 90
    verification_seconds: int = 180
    mock_merchant_url: str = 'http://127.0.0.1:8099'
    browser_executable: str = ''
    session_hours: int = 8
    telegram_enabled: bool = False
    telegram_bot_token: str = ''
    telegram_chat_id: str = ''

    def validate_runtime(self):
        if not 1 <= self.max_browser_contexts <= 4: raise ValueError('MAX_BROWSER_CONTEXTS must be 1..4')
        if not 1 <= self.worker_concurrency <= 4: raise ValueError('WORKER_CONCURRENCY must be 1..4')
        if self.worker_lease_seconds < 30: raise ValueError('Worker lease must be at least 30 seconds')
        if not 1 <= self.session_hours <= 24:
            raise ValueError('SESSION_HOURS must be 1..24')
        if self.app_env == 'production':
            if not self.database_url.startswith('postgresql') or not self.cookie_secure or self.demo_mode:
                raise ValueError('Production requires PostgreSQL, secure cookies, and DEMO_MODE=false')
            from cryptography.fernet import Fernet
            try: Fernet(self.data_encryption_key.encode())
            except Exception: raise ValueError('Production requires a valid DATA_ENCRYPTION_KEY')
            if len(self.nik_hash_key)<32: raise ValueError('Production requires a separate NIK_HASH_KEY')
            if not self.redis_url.startswith('redis://') and not self.redis_url.startswith('rediss://'): raise ValueError('Redis URL required')
            if '*' in self.allowed_hosts or 'testserver' in self.allowed_hosts:
                raise ValueError('Production requires explicit public ALLOWED_HOSTS')

@lru_cache
def settings():
    value = Settings()
    value.validate_runtime()
    return value
