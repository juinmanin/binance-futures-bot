"""Initial database schema

Revision ID: 001_initial
Revises: 
Create Date: 2024-01-21 16:50:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY


# revision identifiers, used by Alembic.
revision = '001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 사용자 테이블
    op.create_table(
        'users',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('email', sa.String(255), unique=True, nullable=False),
        sa.Column('hashed_password', sa.String(255), nullable=False),
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.Column('is_2fa_enabled', sa.Boolean(), default=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), onupdate=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index('ix_users_email', 'users', ['email'])
    
    # API 키 테이블
    op.create_table(
        'api_keys',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', UUID(as_uuid=True), nullable=False),
        sa.Column('exchange', sa.String(50), nullable=False, default='binance'),
        sa.Column('encrypted_api_key', sa.Text(), nullable=False),
        sa.Column('encrypted_api_secret', sa.Text(), nullable=False),
        sa.Column('is_testnet', sa.Boolean(), default=True),
        sa.Column('ip_whitelist', ARRAY(sa.Text())),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    )
    
    # 거래 기록 테이블
    op.create_table(
        'trades',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', UUID(as_uuid=True), nullable=False),
        sa.Column('symbol', sa.String(20), nullable=False),
        sa.Column('side', sa.String(10), nullable=False),
        sa.Column('position_side', sa.String(10)),
        sa.Column('order_type', sa.String(20), nullable=False),
        sa.Column('quantity', sa.Numeric(20, 8), nullable=False),
        sa.Column('price', sa.Numeric(20, 8)),
        sa.Column('executed_price', sa.Numeric(20, 8)),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('strategy_name', sa.String(50)),
        sa.Column('signal_source', JSONB),
        sa.Column('pnl', sa.Numeric(20, 8)),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('executed_at', sa.DateTime()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
    )
    
    # 전략 설정 테이블
    op.create_table(
        'strategy_configs',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('symbols', ARRAY(sa.Text()), nullable=False),
        sa.Column('timeframe', sa.String(10), default='1h'),
        sa.Column('k_value', sa.Numeric(3, 2), default=0.5),
        sa.Column('rsi_overbought', sa.Integer(), default=80),
        sa.Column('rsi_oversold', sa.Integer(), default=20),
        sa.Column('fund_flow_threshold', sa.Integer(), default=10),
        sa.Column('max_position_pct', sa.Numeric(5, 2), default=1.0),
        sa.Column('stop_loss_pct', sa.Numeric(5, 2), default=2.0),
        sa.Column('take_profit_ratio', sa.Numeric(3, 1), default=2.0),
        sa.Column('is_active', sa.Boolean(), default=False),
        sa.Column('mode', sa.String(20), default='paper'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), onupdate=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
    )


def downgrade() -> None:
    op.drop_table('strategy_configs')
    op.drop_table('trades')
    op.drop_table('api_keys')
    op.drop_index('ix_users_email')
    op.drop_table('users')
