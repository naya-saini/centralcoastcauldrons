"""add carts and items tables

Revision ID: 6dc6a022b566
Revises: ff0d68973417
Create Date: 2026-09-04 14:59:17.989567

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6dc6a022b566'
down_revision: Union[str, None] = 'ff0d68973417'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    """Upgrade schema."""

    op.create_table(
        "carts",

        sa.Column(
            "cart_id",
            sa.Integer(),
            primary_key=True,
        ),

        sa.Column(
            "customer_id",
            sa.String(),
            nullable=False,
        ),

        sa.Column(
            "customer_name",
            sa.String(),
            nullable=False,
        ),

        sa.Column(
            "status",
            sa.String(),
            nullable=False,
            server_default="open",
        ),

        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )

    op.create_table(
        "cart_items",

        sa.Column(
            "cart_item_id",
            sa.Integer(),
            primary_key=True,
        ),

        sa.Column(
            "cart_id",
            sa.Integer(),
            sa.ForeignKey("carts.cart_id"),
            nullable=False,
        ),

        sa.Column(
            "potion_id",
            sa.Integer(),
            sa.ForeignKey("potions.potion_id"),
            nullable=False,
        ),

        sa.Column(
            "quantity",
            sa.Integer(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_table("cart_items")
    op.drop_table("carts")