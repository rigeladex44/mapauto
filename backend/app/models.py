import time
from sqlalchemy import String, Integer, Float, Boolean, ForeignKey, JSON, Text, ForeignKeyConstraint, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base

class Tenant(Base):
    __tablename__ = "tenants"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    active: Mapped[bool] = mapped_column(Boolean, default=True)

class TenantScoped:
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False, default=1, index=True)


class User(TenantScoped, Base):
    __table_args__ = (UniqueConstraint("tenant_id", "id", name="uq_user_tenant_id"),)
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True)
    password_hash: Mapped[str] = mapped_column(String(300))
    role: Mapped[str] = mapped_column(String(20), default='viewer')
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    expires_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[float] = mapped_column(Float, default=0)

class Session(Base):
    __tablename__ = 'sessions'
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    csrf: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[float] = mapped_column(Float)

class Merchant(TenantScoped, Base):
    __table_args__ = (UniqueConstraint("tenant_id", "id", name="uq_merchant_tenant_id"),)
    __tablename__ = 'merchants'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    reference: Mapped[str] = mapped_column(String(100), unique=True)
    authorized: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    filters: Mapped[list] = mapped_column(JSON, default=lambda:['RUMAH TANGGA','USAHA MIKRO'])
    stock: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stock_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    stock_simulated: Mapped[bool] = mapped_column(Boolean, default=False)

class Job(TenantScoped, Base):
    __table_args__ = (UniqueConstraint("tenant_id", "id", name="uq_job_tenant_id"),
        ForeignKeyConstraint(['tenant_id','merchant_id'],['merchants.tenant_id','merchants.id'],name='fk_job_merchant_tenant'),
        ForeignKeyConstraint(['tenant_id','created_by'],['users.tenant_id','users.id'],name='fk_job_user_tenant'))
    __tablename__ = 'jobs'
    id: Mapped[int] = mapped_column(primary_key=True)
    merchant_id: Mapped[int] = mapped_column(ForeignKey('merchants.id'))
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    kind: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(30), default='queued', index=True)
    simulated: Mapped[bool] = mapped_column(Boolean, default=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
    updated_at: Mapped[float] = mapped_column(Float, default=time.time)
    worker_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    result: Mapped[str] = mapped_column(Text, default='')
    batch_id: Mapped[int | None] = mapped_column(ForeignKey('batches.id'), nullable=True)
    nik_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    nik_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    nik_masked: Mapped[str | None] = mapped_column(String(24), nullable=True)
    submission_key: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    phase: Mapped[str] = mapped_column(String(40), default='preparing')
    lease_until: Mapped[float] = mapped_column(Float, default=0)
    fencing_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    scenario: Mapped[str] = mapped_column(String(40), default='normal')

class Worker(TenantScoped, Base):
    __tablename__ = 'workers'
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    heartbeat: Mapped[float] = mapped_column(Float, default=time.time)
    paused: Mapped[bool] = mapped_column(Boolean, default=False)

class Audit(TenantScoped, Base):
    __tablename__ = 'audit'
    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    action: Mapped[str] = mapped_column(String(100))
    target: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[float] = mapped_column(Float, default=time.time)

class SystemSetting(TenantScoped, Base):
    __tablename__ = 'system_settings'
    tenant_id: Mapped[int] = mapped_column(ForeignKey('tenants.id'), primary_key=True, default=1)
    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)

class Notification(TenantScoped, Base):
    __tablename__ = 'notifications'
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey('jobs.id'), unique=True)
    status: Mapped[str] = mapped_column(String(30), default='pending')

class Batch(TenantScoped, Base):
    __table_args__ = (UniqueConstraint("tenant_id", "id", name="uq_batch_tenant_id"),
        ForeignKeyConstraint(['tenant_id','merchant_id'],['merchants.tenant_id','merchants.id'],name='fk_batch_merchant_tenant'),
        ForeignKeyConstraint(['tenant_id','created_by'],['users.tenant_id','users.id'],name='fk_batch_user_tenant'))
    __tablename__ = 'batches'
    id: Mapped[int] = mapped_column(primary_key=True)
    merchant_id: Mapped[int] = mapped_column(ForeignKey('merchants.id'))
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    status: Mapped[str] = mapped_column(String(40), default='preview')
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True)
    request_digest: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
    expires_at: Mapped[float] = mapped_column(Float, default=lambda: time.time()+3600)

class Verification(TenantScoped, Base):
    __tablename__ = 'verifications'
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey('jobs.id'), unique=True)
    status: Mapped[str] = mapped_column(String(30), default='waiting')
    response_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[float] = mapped_column(Float)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    operator_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

class Reconciliation(TenantScoped, Base):
    __tablename__ = 'reconciliations'
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey('jobs.id'), unique=True)
    operator_id: Mapped[int] = mapped_column(Integer)
    outcome: Mapped[str] = mapped_column(String(30))
    evidence_encrypted: Mapped[str] = mapped_column(Text)

class MerchantGrant(TenantScoped, Base):
    __tablename__='merchant_grants'
    __table_args__=(UniqueConstraint('user_id','merchant_id'),ForeignKeyConstraint(['tenant_id','merchant_id'],['merchants.tenant_id','merchants.id']),ForeignKeyConstraint(['tenant_id','user_id'],['users.tenant_id','users.id']))
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    merchant_id: Mapped[int] = mapped_column(ForeignKey('merchants.id'))
