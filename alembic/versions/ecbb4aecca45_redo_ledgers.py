"""redo ledgers

Revision ID: ecbb4aecca45
Revises: fa5c4a182499
Create Date: 2026-10-05 22:32:29.212468

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ecbb4aecca45'
down_revision: Union[str, None] = 'fa5c4a182499'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        drop table if exists account_ledger_entries;
        drop table if exists account_transactions;
        drop table if exists accounts;
        
        create table inventory_transactions (
            id          serial primary key,
            created_at  timestamptz not null default now(),
            description text
        );

        create table ledger_entries (
            id             serial primary key,
            transaction_id int  not null references inventory_transactions(id),
            item           text not null,
            change         int  not null
        );
        create index on ledger_entries (item);

        create table processed_requests (
            endpoint   text   not null,
            order_id   bigint not null,
            response   jsonb,
            created_at timestamptz not null default now(),
            primary key (endpoint, order_id)
        );

        create view inventory_balances as
        select item, sum(change)::int as balance
        from ledger_entries
        group by item;
    """)


def downgrade() -> None:
    op.execute("""
        drop view inventory_balances;
        drop table processed_requests;
        drop table ledger_entries;
        drop table inventory_transactions;
    """)