"""fix cart customer fields

Revision ID: 24394af638fb
Revises: afeb110b8180
Create Date: 2026-09-16 08:36:52.322640

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '24394af638fb'
down_revision: Union[str, None] = '6dc6a022b566'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass