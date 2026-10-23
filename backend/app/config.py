from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    app_env: str = 'development'
    database_url: str = 'sqlite:///./mapauto.db'
    cookie_secure: bool = False
    allowed_hosts: str = 'localhost,127.0.0.1,testserver'
    demo_mode: bool = False
    session_hours: int = 8
    telegram_enabled: bool = False
    telegram_bot_token: str = ''
    telegram_chat_id: str = ''

    def validate_runtime(self):
        if not 1 <= self.session_hours <= 24:
            raise ValueError('SESSION_HOURS must be 1..24')
        if self.app_env == 'production':
            if not self.database_url.startswith('postgresql') or not self.cookie_secure or self.demo_mode:
                raise ValueError('Production requires PostgreSQL, secure cookies, and DEMO_MODE=false')
            if '*' in self.allowed_hosts or 'testserver' in self.allowed_hosts:
                raise ValueError('Production requires explicit public ALLOWED_HOSTS')

@lru_cache
def settings():
    value = Settings()
    value.validate_runtime()
    return value
