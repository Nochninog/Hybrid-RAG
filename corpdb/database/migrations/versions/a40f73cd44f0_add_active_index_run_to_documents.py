"""add active index run to documents

Revision ID: a40f73cd44f0
Revises: 36c8aaeee5de
Create Date: 2026-10-22 20:36:24.306345

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a40f73cd44f0'
down_revision: Union[str, Sequence[str], None] = '36c8aaeee5de'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("active_index_run_id", sa.UUID(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("documents", "active_index_run_id")