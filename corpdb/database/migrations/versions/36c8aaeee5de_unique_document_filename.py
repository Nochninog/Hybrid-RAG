"""unique document filename

Revision ID: 36c8aaeee5de
Revises: aecf147a9098
Create Date: 2026-10-15 21:39:37.984516

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '36c8aaeee5de'
down_revision: Union[str, Sequence[str], None] = 'aecf147a9098'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_documents_bucket_filename",
        "documents",
        ["storage_bucket", "filename"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_documents_bucket_filename",
        "documents",
        type_="unique",
    )
