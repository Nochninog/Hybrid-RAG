"""add_wiki_page_links

Revision ID: e7397a54508d
Revises: b728c941ae63
Create Date: 2026-11-03 19:50:31.756090

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e7397a54508d'
down_revision: Union[str, Sequence[str], None] = 'b728c941ae63'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "wiki_page_links",   
        sa.Column(
            "source_page_id",
            sa.Integer(),
            sa.ForeignKey("wiki_pages.id"),
            primary_key=True,
        ),
        sa.Column(
            "target_page_id",
            sa.Integer(),
            sa.ForeignKey("wiki_pages.id"),
            primary_key=True,
        ),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "source_page_id <> target_page_id",
            name="ck_wiki_page_links_no_self_link",
        ),
        sa.CheckConstraint(
            "length(trim(explanation)) > 0",
            name="ck_wiki_page_links_explanation_not_blank",
        ),
    )
    op.create_index(
    "ix_wiki_page_links_target_page_id",
    "wiki_page_links",
    ["target_page_id"],
    )


def downgrade() -> None:
    op.drop_table("wiki_page_links")
