"""Initial web schema; no import of legacy accounts or personal data."""
from alembic import op
import sqlalchemy as sa
revision='0001'
down_revision=None
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('users',sa.Column('id',sa.Integer,primary_key=True),sa.Column('username',sa.String(80),unique=True,nullable=False),sa.Column('password_hash',sa.String(300),nullable=False),sa.Column('role',sa.String(20),nullable=False),sa.Column('active',sa.Boolean,nullable=False),sa.Column('expires_at',sa.Float),sa.Column('failed_logins',sa.Integer,nullable=False),sa.Column('locked_until',sa.Float,nullable=False))
    op.create_table('sessions',sa.Column('token_hash',sa.String(64),primary_key=True),sa.Column('user_id',sa.Integer,sa.ForeignKey('users.id'),nullable=False),sa.Column('csrf',sa.String(64),nullable=False),sa.Column('expires_at',sa.Float,nullable=False))
    op.create_table('merchants',sa.Column('id',sa.Integer,primary_key=True),sa.Column('name',sa.String(100),nullable=False),sa.Column('reference',sa.String(100),unique=True,nullable=False),sa.Column('authorized',sa.Boolean,nullable=False),sa.Column('active',sa.Boolean,nullable=False),sa.Column('filters',sa.JSON,nullable=False),sa.Column('stock',sa.Integer),sa.Column('stock_at',sa.Float),sa.Column('stock_simulated',sa.Boolean,nullable=False))
    op.create_table('jobs',sa.Column('id',sa.Integer,primary_key=True),sa.Column('merchant_id',sa.Integer,sa.ForeignKey('merchants.id'),nullable=False),sa.Column('created_by',sa.Integer,sa.ForeignKey('users.id'),nullable=False),sa.Column('kind',sa.String(30),nullable=False),sa.Column('status',sa.String(30),nullable=False),sa.Column('simulated',sa.Boolean,nullable=False),sa.Column('quantity',sa.Integer,nullable=False),sa.Column('created_at',sa.Float,nullable=False),sa.Column('updated_at',sa.Float,nullable=False),sa.Column('worker_id',sa.String(80)),sa.Column('result',sa.Text,nullable=False))
    op.create_index('ix_jobs_status','jobs',['status'])
    op.create_table('workers',sa.Column('id',sa.String(80),primary_key=True),sa.Column('heartbeat',sa.Float,nullable=False),sa.Column('paused',sa.Boolean,nullable=False))
    op.create_table('audit',sa.Column('id',sa.Integer,primary_key=True),sa.Column('actor_id',sa.Integer),sa.Column('action',sa.String(100),nullable=False),sa.Column('target',sa.String(100),nullable=False),sa.Column('created_at',sa.Float,nullable=False))
    op.create_table('system_settings',sa.Column('key',sa.String(60),primary_key=True),sa.Column('value',sa.JSON,nullable=False))
    op.create_table('notifications',sa.Column('id',sa.Integer,primary_key=True),sa.Column('job_id',sa.Integer,sa.ForeignKey('jobs.id'),unique=True,nullable=False),sa.Column('status',sa.String(30),nullable=False))

def downgrade():
    for table in ['notifications','system_settings','audit','workers','jobs','merchants','sessions','users']: op.drop_table(table)
