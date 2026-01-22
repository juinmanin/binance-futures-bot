"""Add pending_signals table

Revision ID: 003_pending_signals
Revises: 002_api_key_enhancements
Create Date: 2026-01-21 23:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision = '003_pending_signals'
down_revision = '002_api_key_enhancements'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 대기 중인 거래 신호 테이블
    op.create_table(
        'pending_signals',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', UUID(as_uuid=True), nullable=False),
        sa.Column('symbol', sa.String(20), nullable=False),
        sa.Column('action', sa.String(10), nullable=False),
        sa.Column('entry_price', sa.Numeric(20, 8), nullable=False),
        sa.Column('stop_loss', sa.Numeric(20, 8), nullable=False),
        sa.Column('take_profit_1', sa.Numeric(20, 8), nullable=False),
        sa.Column('take_profit_2', sa.Numeric(20, 8), nullable=False),
        sa.Column('position_size', sa.Numeric(20, 8)),
        sa.Column('atr', sa.Numeric(20, 8)),
        sa.Column('confidence', sa.Numeric(3, 2)),
        sa.Column('reason', sa.Text()),
        sa.Column('strategy_name', sa.String(50)),
        sa.Column('status', sa.String(20), default='pending'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('expires_at', sa.DateTime()),
        sa.Column('executed_at', sa.DateTime()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
    )
    
    # 인덱스 생성
    op.create_index('ix_pending_signals_user_status', 'pending_signals', ['user_id', 'status'])


def downgrade() -> None:
    op.drop_index('ix_pending_signals_user_status')
    op.drop_table('pending_signals')
