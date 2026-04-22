"""Slice 14.2: Contracts and projects master foundations

Revision ID: c769a70b05ed
Revises: 07c5651fc193
Create Date: 2026-03-27 02:15:38.132922
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa



# revision identifiers, used by Alembic.
revision = 'c769a70b05ed'
down_revision = '07c5651fc193'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create contracts table
    op.create_table(
        'contracts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('contract_number', sa.String(length=40), nullable=False),
        sa.Column('contract_title', sa.String(length=255), nullable=False),
        sa.Column('customer_id', sa.Integer(), nullable=False),
        sa.Column('contract_type_code', sa.String(length=20), nullable=False),
        sa.Column('currency_code', sa.String(length=3), nullable=False),
        sa.Column('exchange_rate', sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column('base_contract_amount', sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column('start_date', sa.Date(), nullable=True),
        sa.Column('planned_end_date', sa.Date(), nullable=True),
        sa.Column('actual_end_date', sa.Date(), nullable=True),
        sa.Column('status_code', sa.String(length=20), nullable=False),
        sa.Column('billing_basis_code', sa.String(length=20), nullable=True),
        sa.Column('retention_percent', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('reference_number', sa.String(length=100), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('approved_at', sa.Date(), nullable=True),
        sa.Column('approved_by_user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('created_by_user_id', sa.Integer(), nullable=True),
        sa.Column('updated_by_user_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['currency_code'], ['currencies.code'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['approved_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['updated_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('company_id', 'contract_number'),
    )
    op.create_index('ix_contracts_company_id', 'contracts', ['company_id'])
    op.create_index('ix_contracts_customer_id', 'contracts', ['customer_id'])

    # Create projects table
    op.create_table(
        'projects',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('project_code', sa.String(length=40), nullable=False),
        sa.Column('project_name', sa.String(length=255), nullable=False),
        sa.Column('contract_id', sa.Integer(), nullable=True),
        sa.Column('customer_id', sa.Integer(), nullable=True),
        sa.Column('project_type_code', sa.String(length=20), nullable=False),
        sa.Column('project_manager_user_id', sa.Integer(), nullable=True),
        sa.Column('currency_code', sa.String(length=3), nullable=True),
        sa.Column('exchange_rate', sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column('start_date', sa.Date(), nullable=True),
        sa.Column('planned_end_date', sa.Date(), nullable=True),
        sa.Column('actual_end_date', sa.Date(), nullable=True),
        sa.Column('status_code', sa.String(length=20), nullable=False),
        sa.Column('budget_control_mode_code', sa.String(length=20), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('created_by_user_id', sa.Integer(), nullable=True),
        sa.Column('updated_by_user_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['contract_id'], ['contracts.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['project_manager_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['currency_code'], ['currencies.code'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['updated_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('company_id', 'project_code'),
    )
    op.create_index('ix_projects_company_id', 'projects', ['company_id'])
    op.create_index('ix_projects_contract_id', 'projects', ['contract_id'])
    op.create_index('ix_projects_customer_id', 'projects', ['customer_id'])


def downgrade() -> None:
    op.drop_index('ix_projects_customer_id', table_name='projects')
    op.drop_index('ix_projects_contract_id', table_name='projects')
    op.drop_index('ix_projects_company_id', table_name='projects')
    op.drop_table('projects')
    op.drop_index('ix_contracts_customer_id', table_name='contracts')
    op.drop_index('ix_contracts_company_id', table_name='contracts')
    op.drop_table('contracts')
