from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from .config import settings

class Base(DeclarativeBase):
    pass

url = settings().database_url
engine = create_engine(url, pool_pre_ping=True, connect_args={'check_same_thread': False, 'timeout': 30} if url.startswith('sqlite') else {})
SessionLocal = sessionmaker(engine, expire_on_commit=False)

def get_db():
    with SessionLocal() as db:
        yield db

# Scope all public ORM reads/writes, including Session.get and bulk DML.
from sqlalchemy import event
from sqlalchemy.orm import Session as ORMSession, with_loader_criteria

@event.listens_for(ORMSession, 'do_orm_execute')
def tenant_boundary(state):
    tenant_id=state.session.info.get('tenant_id')
    if tenant_id is not None:
        from .models import TenantScoped
        state.statement=state.statement.options(with_loader_criteria(TenantScoped, lambda cls: cls.tenant_id == tenant_id, include_aliases=True))
        allowed=state.session.info.get('merchant_ids')
        if allowed is not None:
            from .models import Merchant, Job, Batch, Verification
            from sqlalchemy import select
            state.statement=state.statement.options(
                with_loader_criteria(Merchant,lambda cls: cls.id.in_(allowed),include_aliases=True),
                with_loader_criteria(Job,lambda cls: cls.merchant_id.in_(allowed),include_aliases=True),
                with_loader_criteria(Batch,lambda cls: cls.merchant_id.in_(allowed),include_aliases=True),
                with_loader_criteria(Verification,lambda cls: cls.job_id.in_(select(Job.id).where(Job.merchant_id.in_(allowed))),include_aliases=True))

@event.listens_for(ORMSession, 'before_flush')
def enforce_tenant_writes(db, *_):
    tenant_id=db.info.get('tenant_id')
    if tenant_id is not None:
        from .models import TenantScoped
        for obj in db.new | db.dirty | db.deleted:
            if isinstance(obj,TenantScoped):
                if obj in db.new and obj.tenant_id is None: obj.tenant_id=tenant_id
                if obj.tenant_id!=tenant_id: raise ValueError('Cross-tenant write rejected')
