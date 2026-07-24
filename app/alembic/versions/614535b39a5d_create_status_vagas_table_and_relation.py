"""create_status_vagas_table_and_relation

Revision ID: 614535b39a5d
Revises: fca41a0c1e74
Create Date: 2026-07-23 02:37:39.371910

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '614535b39a5d'
down_revision: Union[str, Sequence[str], None] = 'fca41a0c1e74'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # Cria a tabela status_vagas
    op.create_table(
        'status_vagas',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )
    op.create_index(op.f('ix_status_vagas_id'), 'status_vagas', ['id'], unique=False)

    # Usa o modo BATCH para adicionar a coluna e a Foreign Key no SQLite
    with op.batch_alter_table('vagas', schema=None) as batch_op:
        batch_op.add_column(sa.Column('status_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_vagas_status_id', 'status_vagas', ['status_id'], ['id'])


def downgrade() -> None:
    # Reverte as alterações utilizando o modo BATCH
    with op.batch_alter_table('vagas', schema=None) as batch_op:
        batch_op.drop_constraint('fk_vagas_status_id', type_='foreignkey')
        batch_op.drop_column('status_id')

    op.drop_index(op.f('ix_status_vagas_id'), table_name='status_vagas')
    op.drop_table('status_vagas')
    # ### end Alembic commands ###
