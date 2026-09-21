"""add ledger tables

Revision ID: d98c0680c287
Revises: 24394af638fb
Create Date: 2026-09-21 12:55:14.809231

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd98c0680c287'
down_revision: Union[str, None] = '24394af638fb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE accounts(
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL
        );
        """
    )

    op.execute("""
        CREATE TABLE account_transactions(
            id SERIAL PRIMARY KEY,
            created_at TIMESTAMP DEFAULT now(),
            description TEXT NOT NULL
        );
        """
    )

    op.execute("""
        CREATE TABLE account_ledger_entries(
            id SERIAL PRIMARY KEY,
            account_id INT NOT NULL,
            account_transaction_id INT NOT NULL,
            change INT NOT NULL,

            FOREIGN KEY (account_id)
                REFERENCES accounts(id),

            FOREIGN KEY (account_transaction_id)
                REFERENCES account_transactions(id)
        );
        """
    )

    op.execute("""
        CREATE TABLE processed_requests(
            order_id UUID PRIMARY KEY,
            response JSONB NOT NULL
        );
        """
    )

def downgrade() -> None:
    op.execute("""
        DROP TABLE account_ledger_entries;
        DROP TABLE account_transactions;
        DROP TABLE processed_requests;
        DROP TABLE accounts;
    """)
