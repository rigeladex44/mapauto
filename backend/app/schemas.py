from pydantic import BaseModel, Field, ConfigDict
from typing import Literal

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')
class Login(Strict):
    username: str = Field(min_length=3,max_length=80,pattern=r'^[a-zA-Z0-9_.-]+$')
    password: str = Field(min_length=1,max_length=128)
class UserCreate(Login):
    password: str = Field(min_length=12,max_length=128)
    role: Literal['admin','operator','viewer']='viewer'
class UserUpdate(Strict):
    role: Literal['admin','operator','viewer']
    active: bool
    extend_days: int = Field(default=0,ge=0,le=3650)
class PasswordChange(Strict):
    current_password: str = Field(min_length=1,max_length=128)
    new_password: str = Field(min_length=12,max_length=128)
class MerchantInput(Strict):
    name: str = Field(min_length=2,max_length=100)
    reference: str = Field(min_length=2,max_length=100,pattern=r'^[a-zA-Z0-9_.-]+$')
    authorized: bool
    active: bool=True
    filters: list[str] = Field(default_factory=lambda:['RUMAH TANGGA','USAHA MIKRO'])
class JobInput(Strict):
    merchant_id: int
    kind: Literal['stock','transaction']
    simulated: bool=True
    quantity: int = Field(default=1,ge=1,le=100)
class WorkerInput(Strict):
    paused: bool
class SystemInput(Strict):
    telegram_notifications: bool
