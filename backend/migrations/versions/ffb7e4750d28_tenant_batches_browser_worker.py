"""Tenant boundary and encrypted batch/verification state. Existing rows → tenant 1.
No credential import, no destructive down migration.
"""
from alembic import op
import sqlalchemy as sa
revision='ffb7e4750d28'
down_revision='0001'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('tenants',sa.Column('id',sa.Integer,primary_key=True),sa.Column('name',sa.String(100),nullable=False),sa.Column('active',sa.Boolean,nullable=False))
    op.bulk_insert(sa.table('tenants',sa.column('id',sa.Integer),sa.column('name',sa.String),sa.column('active',sa.Boolean)),[{'id':1,'name':'Migrated workspace','active':True}])
    for table in ['users','merchants','jobs','workers','audit','notifications','system_settings']:
        op.add_column(table,sa.Column('tenant_id',sa.Integer,nullable=False,server_default='1'))
        with op.batch_alter_table(table,naming_convention={'pk':'pk_%(table_name)s'}) as b:
            b.create_foreign_key('fk_'+table+'_tenant','tenants',['tenant_id'],['id'])
            if table!='system_settings':b.create_index('ix_'+table+'_tenant_id',['tenant_id'])
            if table in ['users','merchants','jobs']:
                name={'users':'user','merchants':'merchant','jobs':'job'}[table]
                b.create_unique_constraint('uq_'+name+'_tenant_id',['tenant_id','id'])
    pk=sa.inspect(op.get_bind()).get_pk_constraint('system_settings')['name'] or 'pk_system_settings'
    with op.batch_alter_table('system_settings',naming_convention={'pk':'pk_%(table_name)s'}) as b:
        b.drop_constraint(pk,type_='primary');b.create_primary_key('pk_system_settings',['tenant_id','key'])
    op.create_table('batches',sa.Column('id',sa.Integer,primary_key=True),sa.Column('tenant_id',sa.Integer,sa.ForeignKey('tenants.id'),nullable=False),sa.Column('merchant_id',sa.Integer,sa.ForeignKey('merchants.id'),nullable=False),sa.Column('created_by',sa.Integer,sa.ForeignKey('users.id'),nullable=False),sa.Column('status',sa.String(40),nullable=False),sa.Column('idempotency_key',sa.String(64),unique=True,nullable=False),sa.Column('request_digest',sa.String(64),nullable=False),sa.Column('created_at',sa.Float,nullable=False),sa.Column('expires_at',sa.Float,nullable=False),sa.UniqueConstraint('tenant_id','id',name='uq_batch_tenant_id'),sa.ForeignKeyConstraint(['tenant_id','merchant_id'],['merchants.tenant_id','merchants.id'],name='fk_batch_merchant_tenant'),sa.ForeignKeyConstraint(['tenant_id','created_by'],['users.tenant_id','users.id'],name='fk_batch_user_tenant'))
    op.create_index('ix_batches_tenant_id','batches',['tenant_id'])
    with op.batch_alter_table('jobs') as b:
        b.add_column(sa.Column('batch_id',sa.Integer,nullable=True))
        for name,type_,nullable,default in [('nik_encrypted',sa.Text,True,None),('nik_digest',sa.String(64),True,None),('nik_masked',sa.String(24),True,None),('submission_key',sa.String(64),True,None),('phase',sa.String(40),False,'preparing'),('lease_until',sa.Float,False,'0'),('fencing_token',sa.String(64),True,None),('scenario',sa.String(40),False,'normal')]:
            b.add_column(sa.Column(name,type_,nullable=nullable,server_default=default))
        b.create_unique_constraint('uq_job_submission_key',['submission_key'])
        b.create_foreign_key('fk_job_batch','batches',['batch_id'],['id'])
        b.create_foreign_key('fk_job_merchant_tenant','merchants',['tenant_id','merchant_id'],['tenant_id','id'])
        b.create_foreign_key('fk_job_user_tenant','users',['tenant_id','created_by'],['tenant_id','id'])
    op.create_table('verifications',sa.Column('id',sa.Integer,primary_key=True),sa.Column('tenant_id',sa.Integer,sa.ForeignKey('tenants.id'),nullable=False),sa.Column('job_id',sa.Integer,sa.ForeignKey('jobs.id'),unique=True,nullable=False),sa.Column('status',sa.String(30),nullable=False),sa.Column('response_encrypted',sa.Text),sa.Column('expires_at',sa.Float,nullable=False),sa.Column('attempts',sa.Integer,nullable=False),sa.Column('operator_id',sa.Integer))
    op.create_index('ix_verifications_tenant_id','verifications',['tenant_id'])
    op.create_table('reconciliations',sa.Column('id',sa.Integer,primary_key=True),sa.Column('tenant_id',sa.Integer,sa.ForeignKey('tenants.id'),nullable=False),sa.Column('job_id',sa.Integer,sa.ForeignKey('jobs.id'),unique=True,nullable=False),sa.Column('operator_id',sa.Integer,nullable=False),sa.Column('outcome',sa.String(30),nullable=False),sa.Column('evidence_encrypted',sa.Text,nullable=False))
    op.create_index('ix_reconciliations_tenant_id','reconciliations',['tenant_id'])
    op.create_table('merchant_grants',sa.Column('id',sa.Integer,primary_key=True),sa.Column('tenant_id',sa.Integer,sa.ForeignKey('tenants.id'),nullable=False),sa.Column('user_id',sa.Integer,sa.ForeignKey('users.id'),nullable=False),sa.Column('merchant_id',sa.Integer,sa.ForeignKey('merchants.id'),nullable=False),sa.UniqueConstraint('user_id','merchant_id'),sa.ForeignKeyConstraint(['tenant_id','user_id'],['users.tenant_id','users.id']),sa.ForeignKeyConstraint(['tenant_id','merchant_id'],['merchants.tenant_id','merchants.id']))
    op.create_index('ix_merchant_grants_tenant_id','merchant_grants',['tenant_id'])


def downgrade():
    raise RuntimeError('Tenant migration is irreversible: restore a reviewed encrypted backup; never discard tenant/verification history automatically')
