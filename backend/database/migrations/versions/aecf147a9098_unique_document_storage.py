"""unique document storage

Revision ID: aecf147a9098
Revises: 9d06d54a2b55
Create Date: 2026-10-15 18:39:40.154884

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'aecf147a9098'
down_revision: Union[str, Sequence[str], None] = '9d06d54a2b55'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_documents_storage_location",
        "documents",
        ["storage_bucket", "storage_key"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_documents_storage_location",
        "documents",
        type_="unique",
    )