"""Add Signal and BacktestResult models

Revision ID: 002_strategy_signals
Revises: 001_initial
Create Date: 2026-01-21

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '002_strategy_signals'
down_revision = '001_initial'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create signals table
    op.create_table(
        'signals',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('strategy_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('symbol', sa.String(length=20), nullable=False),
        sa.Column('timeframe', sa.String(length=10), nullable=False),
        sa.Column('action', sa.String(length=10), nullable=False),
        sa.Column('confidence', sa.Numeric(precision=3, scale=2), nullable=False),
        sa.Column('entry_price', sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column('stop_loss', sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column('take_profit_1', sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column('take_profit_2', sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column('position_size', sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('indicators', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('expired_at', sa.DateTime(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=True),
        sa.ForeignKeyConstraint(['strategy_id'], ['strategy_configs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_signals_strategy_id'), 'signals', ['strategy_id'], unique=False)
    op.create_index(op.f('ix_signals_created_at'), 'signals', ['created_at'], unique=False)
    
    # Create backtest_results table
    op.create_table(
        'backtest_results',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('strategy_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('symbol', sa.String(length=20), nullable=False),
        sa.Column('start_date', sa.DateTime(), nullable=False),
        sa.Column('end_date', sa.DateTime(), nullable=False),
        sa.Column('initial_capital', sa.Numeric(precision=20, scale=2), nullable=False),
        sa.Column('final_capital', sa.Numeric(precision=20, scale=2), nullable=False),
        sa.Column('total_return', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('win_rate', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('profit_factor', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('max_drawdown', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('sharpe_ratio', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('total_trades', sa.Integer(), nullable=True),
        sa.Column('avg_profit', sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column('avg_loss', sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column('trades_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['strategy_id'], ['strategy_configs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_backtest_results_strategy_id'), 'backtest_results', ['strategy_id'], unique=False)
    op.create_index(op.f('ix_backtest_results_created_at'), 'backtest_results', ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_backtest_results_created_at'), table_name='backtest_results')
    op.drop_index(op.f('ix_backtest_results_strategy_id'), table_name='backtest_results')
    op.drop_table('backtest_results')
    
    op.drop_index(op.f('ix_signals_created_at'), table_name='signals')
    op.drop_index(op.f('ix_signals_strategy_id'), table_name='signals')
    op.drop_table('signals')
