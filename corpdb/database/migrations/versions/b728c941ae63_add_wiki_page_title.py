"""Add a title to Wiki pages.

Revision ID: b728c941ae63
Revises: a40f73cd44f0
"""

from alembic import op
import sqlalchemy as sa

revision = "b728c941ae63"
down_revision = "a40f73cd44f0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("wiki_pages", sa.Column("title", sa.Text(), nullable=True))
    op.execute("UPDATE wiki_pages SET title = 'Без названия' WHERE title IS NULL")
    op.alter_column("wiki_pages", "title", nullable=False)


def downgrade() -> None:
    op.drop_column("wiki_pages", "title")
