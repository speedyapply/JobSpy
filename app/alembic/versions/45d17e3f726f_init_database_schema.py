"""init_database_schema

Revision ID: 45d17e3f726f
Revises: 
Create Date: 2026-07-24

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# Mantanha o revision id original que veio no arquivo criado!
revision: str = '45d17e3f726f'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Cria tabela status_vagas
    op.create_table(
        'status_vagas',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )
    op.create_index(op.f('ix_status_vagas_id'), 'status_vagas', ['id'], unique=False)

    # 2. Cria tabela vagas
    op.create_table(
        'vagas',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(), nullable=True),
        sa.Column('company', sa.String(), nullable=True),
        sa.Column('company_url', sa.String(), nullable=True),
        sa.Column('job_url', sa.String(), nullable=True),
        sa.Column('location', sa.String(), nullable=True),
        sa.Column('city', sa.String(), nullable=True),
        sa.Column('state', sa.String(), nullable=True),
        sa.Column('country', sa.String(), nullable=True),
        sa.Column('is_remote', sa.Boolean(), nullable=True),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('job_type', sa.String(), nullable=True),
        sa.Column('interval', sa.String(), nullable=True),
        sa.Column('min_amount', sa.Float(), nullable=True),
        sa.Column('max_amount', sa.Float(), nullable=True),
        sa.Column('currency', sa.String(), nullable=True),
        sa.Column('date_posted', sa.String(), nullable=True),
        sa.Column('emails', sa.String(), nullable=True),
        sa.Column('status_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['status_id'], ['status_vagas.id'], name='fk_vagas_status_id'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('job_url')
    )
    op.create_index(op.f('ix_vagas_id'), 'vagas', ['id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_vagas_id'), table_name='vagas')
    op.drop_table('vagas')
    op.drop_index(op.f('ix_status_vagas_id'), table_name='status_vagas')
    op.drop_table('status_vagas')