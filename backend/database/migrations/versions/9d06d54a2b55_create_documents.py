"""create documents

Revision ID: 9d06d54a2b55
Revises: a9f7b53b2876
Create Date: 2026-10-15 16:45:30.223793

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9d06d54a2b55'
down_revision: Union[str, Sequence[str], None] = 'a9f7b53b2876'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("storage_bucket", sa.Text(), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
    )

    op.create_table(
        "wiki_pages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("content", sa.Text(), nullable=False),
    )

    op.create_table(
        "wiki_page_documents",
        sa.Column(
            "wiki_page_id",
            sa.Integer(),
            sa.ForeignKey("wiki_pages.id"),
            primary_key=True,
        ),
        sa.Column(
            "document_id",
            sa.Integer(),
            sa.ForeignKey("documents.id"),
            primary_key=True,
        ),
    )



def downgrade() -> None:
    op.drop_table("wiki_page_documents")
    op.drop_table("wiki_pages")
    op.drop_table("documents")
