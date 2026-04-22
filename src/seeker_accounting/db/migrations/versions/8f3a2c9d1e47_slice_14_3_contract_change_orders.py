"""Slice 14.3: Contract change orders

Revision ID: 8f3a2c9d1e47
Revises: c769a70b05ed
Create Date: 2026-03-27 12:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8f3a2c9d1e47'
down_revision = 'a1b2c3d4e5f7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'contract_change_orders',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('contract_id', sa.Integer(), nullable=False),
        sa.Column('change_order_number', sa.String(length=40), nullable=False),
        sa.Column('change_order_date', sa.Date(), nullable=False),
        sa.Column('status_code', sa.String(length=20), nullable=False),
        sa.Column('change_type_code', sa.String(length=20), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('contract_amount_delta', sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column('days_extension', sa.Integer(), nullable=True),
        sa.Column('effective_date', sa.Date(), nullable=True),
        sa.Column('approved_at', sa.DateTime(), nullable=True),
        sa.Column('approved_by_user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['contract_id'], ['contracts.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['approved_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('company_id', 'change_order_number'),
    )
    op.create_index('ix_contract_change_orders_company_id', 'contract_change_orders', ['company_id'])
    op.create_index('ix_contract_change_orders_contract_id', 'contract_change_orders', ['contract_id'])


def downgrade() -> None:
    op.drop_index('ix_contract_change_orders_contract_id', table_name='contract_change_orders')
    op.drop_index('ix_contract_change_orders_company_id', table_name='contract_change_orders')
    op.drop_table('contract_change_orders')
