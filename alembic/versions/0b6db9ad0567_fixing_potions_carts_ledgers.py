"""fixing potions carts ledgers

Revision ID: 0b6db9ad0567
Revises: ecbb4aecca45
Create Date: 2026-10-06 23:51:41.208659

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0b6db9ad0567'
down_revision: Union[str, None] = 'ecbb4aecca45'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        drop view if exists potion_inventory;
        drop table if exists potion_sales;
        drop table if exists cart_items;
        drop table if exists carts;
        drop table if exists customers;
        drop table if exists potions;

        create table potions (
            id     serial primary key,
            sku    text not null unique,
            name   text not null,
            red    int not null default 0,
            green  int not null default 0,
            blue   int not null default 0,
            dark   int not null default 0,
            price  int not null default 50,
            active boolean not null default true,
            check(red + green+ blue + dark = 100),
            unique (red, green, blue, dark)
        );

        insert into potions (sku, name, red, green, blue, dark, price) values
            ('red_potion',    'Red Potion',    100, 0, 0, 0, 50),
            ('green_potion',  'Green Potion',  0, 100, 0, 0, 50),
            ('blue_potion',   'Blue Potion',   0, 0, 100, 0, 50),
            ('purple_potion', 'Purple Potion', 50, 0, 50, 0, 70);

        create table customers (
            id          serial primary key,
            external_id text not null unique,
            name        text not null,
            class       text,
            species     text,
            level       int
        );

        create table carts (
            id          serial primary key,
            customer_id int not null references customers(id),
            created_at  timestamptz not null default now()
        );

        create table cart_items (
            cart_id   int not null references carts(id) on delete cascade,
            potion_id int not null references potions(id),
            quantity  int not null check (quantity > 0),
            primary key (cart_id, potion_id)
        );

        create table potion_sales (
            id             serial primary key,
            transaction_id int not null references inventory_transactions(id),
            cart_id        int not null references carts(id),
            customer_id    int not null references customers(id),
            potion_id      int not null references potions(id),
            quantity       int not null,
            unit_price     int not null,
            sold_at        timestamptz not null default now(),
            day_of_week    text not null,
            hour_of_day    int not null
        );

        -- stock per potion = ledger balance of item 'potion:<sku>'
        create view potion_inventory as
        select p.*, coalesce(b.balance, 0) as stock
        from potions p
        left join inventory_balances b on b.item = 'potion:' || p.sku;
    """)


def downgrade() -> None:
    op.execute("""
        drop view potion_inventory;
        drop table potion_sales;
        drop table cart_items;
        drop table carts;
        drop table customers;
        drop table potions;
    """)
