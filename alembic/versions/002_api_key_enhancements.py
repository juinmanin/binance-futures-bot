"""Add label, is_default, last_used_at to api_keys

Revision ID: 002_api_key_enhancements
Revises: 001_initial
Create Date: 2026-01-21 22:56:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '002_api_key_enhancements'
down_revision = '001_initial'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # API 키 테이블에 새 컬럼 추가
    op.add_column('api_keys', sa.Column('label', sa.String(50), default='Default'))
    op.add_column('api_keys', sa.Column('is_default', sa.Boolean(), default=False))
    op.add_column('api_keys', sa.Column('last_used_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    # 새 컬럼 제거
    op.drop_column('api_keys', 'last_used_at')
    op.drop_column('api_keys', 'is_default')
    op.drop_column('api_keys', 'label')
