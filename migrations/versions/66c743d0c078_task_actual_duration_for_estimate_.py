"""task actual duration for estimate calibration

Separates the ESTIMATE (tasks.duration_min) from REALITY (tasks.actual_min).
Before this, completing a task overwrote the estimate with the actual value, so
no estimate-vs-reality history existed and calibration was impossible.

Revision ID: 66c743d0c078
Revises: d74a38ab7ba0
Create Date: 2026-10-28 07:27:14.731928
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = '66c743d0c078'
down_revision: Union[str, None] = 'd74a38ab7ba0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('tasks', schema=None) as batch_op:
        batch_op.add_column(sa.Column('actual_min', sa.Integer(), nullable=True))
    # Backfill from the old lossy behaviour: rows completed before this revision
    # stored the real duration in duration_min. We mark them as 'actual' only for
    # the ratio sample, keeping the column itself honest (NULL = estimate only).
    op.execute("UPDATE tasks SET actual_min = duration_min WHERE status = 'done'")


def downgrade() -> None:
    # Lossy by nature: the separated estimate cannot be reconstructed, so the
    # column is dropped and pre-existing behaviour (estimate only) is restored.
    with op.batch_alter_table('tasks', schema=None) as batch_op:
        batch_op.drop_column('actual_min')
