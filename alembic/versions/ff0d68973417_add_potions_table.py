"""add potions table

Revision ID: ff0d68973417
Revises: d7f91aacadbe
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "ff0d68973417"
down_revision: Union[str, None] = "d7f91aacadbe"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.create_table(
        "potions",

        sa.Column(
            "potion_id",
            sa.Integer(),
            primary_key=True,
        ),

        sa.Column(
            "sku",
            sa.String(),
            nullable=False,
            unique=True,
        ),

        sa.Column(
            "name",
            sa.String(),
            nullable=False,
        ),

        # Potion recipe percentages
        sa.Column(
            "red",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "green",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "blue",
            sa.Integer(),
            nullable=False,
        ),

        # Finished potion inventory
        sa.Column(
            "quantity",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),

        # Catalog price
        sa.Column(
            "price",
            sa.Integer(),
            nullable=False,
        ),
    )

    # Starting potion types
    op.execute("""
        INSERT INTO potions (
            red,
            green,
            blue,
            name,
            sku,
            price,
            quantity
        )
        VALUES
            (100, 0, 0, 'Red Potion', 'RED_POTION_0', 30, 0),
            (0, 100, 0, 'Green Potion', 'GREEN_POTION_0', 30, 0),
            (0, 0, 100, 'Blue Potion', 'BLUE_POTION_0', 30, 0),
            (50, 0, 50, 'Purple Potion', 'PURPLE_POTION_0', 40, 0),
            (50, 50, 0, 'Brown Potion', 'BROWN_POTION_0', 40, 0),
            (33, 33, 34, 'Black Potion', 'BLACK_POTION_0', 50, 0);
    """)


def downgrade() -> None:
    op.drop_table("potions")