from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field, field_validator
from typing import List

import sqlalchemy

from src.api import auth
from src import database as db


router = APIRouter(
    prefix="/bottler",
    tags=["bottler"],
    dependencies=[Depends(auth.get_api_key)],
)


class PotionMixes(BaseModel):
    potion_type: List[int] = Field(min_length=4, max_length=4)
    quantity: int = Field(gt=0, le=10000)

    @field_validator("potion_type")
    @classmethod
    def validate_potion_type(cls, value):
        if sum(value) != 100:
            raise ValueError("Potion percentages must add up to 100")
        return value



def get_balance(connection, account_name):
    result = connection.execute(
        sqlalchemy.text("""
            SELECT COALESCE(SUM(le.change), 0)
            FROM accounts a
            LEFT JOIN account_ledger_entries le
                ON le.account_id = a.id
            WHERE a.name = :name
        """),
        {"name": account_name},
    )

    return int(result.scalar_one())


def get_account_id(connection, account_name):
    result = connection.execute(
        sqlalchemy.text("""
            SELECT id
            FROM accounts
            WHERE name = :name
            FOR UPDATE
        """),
        {"name": account_name},
    )

    account_id = result.scalar_one_or_none()

    if account_id is None:
        raise ValueError(
            f"Ledger account '{account_name}' does not exist"
        )

    return account_id


def add_ledger_entry(
    connection,
    account_name,
    amount,
    transaction_id,
):
    account_id = get_account_id(connection, account_name)

    connection.execute(
        sqlalchemy.text("""
            INSERT INTO account_ledger_entries (
                account_id,
                account_transaction_id,
                change
            )
            VALUES (
                :account_id,
                :transaction_id,
                :amount
            )
        """),
        {
            "account_id": account_id,
            "transaction_id": transaction_id,
            "amount": amount,
        },
    )


@router.post(
    "/deliver/{order_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def deliver_potions(
    order_id: str,
    potions: List[PotionMixes],
):
    with db.engine.begin() as connection:

        already_processed = connection.execute(
            sqlalchemy.text("""
                SELECT 1
                FROM processed_requests
                WHERE order_id = :order_id
            """),
            {"order_id": order_id},
        ).first()

        if already_processed:
            return
        transaction_id = connection.execute(
            sqlalchemy.text("""
                INSERT INTO account_transactions (description)
                VALUES (:description)
                RETURNING id
            """),
            {
                "description": f"Bottler delivery {order_id}"
            },
        ).scalar_one()


        red_used = 0
        green_used = 0
        blue_used = 0

        delivered = []

        for item in potions:

            recipe = connection.execute(
                sqlalchemy.text("""
                    SELECT red, green, blue
                    FROM potions
                    WHERE sku = :sku
                """),
                {
                    "sku": item.potion_type
                },
            ).first()
            red = item.potion_type[0]
            green = item.potion_type[1]
            blue = item.potion_type[2]

            red_used += red * item.quantity
            green_used += green * item.quantity
            blue_used += blue * item.quantity

            delivered.append(item)

        red_used = red_used // 100
        green_used = green_used // 100
        blue_used = blue_used // 100

        if get_balance(connection, "Red ML") < red_used:
            raise ValueError("Not enough Red ML")

        if get_balance(connection, "Green ML") < green_used:
            raise ValueError("Not enough Green ML")

        if get_balance(connection, "Blue ML") < blue_used:
            raise ValueError("Not enough Blue ML")

        current_potions = connection.execute(
            sqlalchemy.text("""
                SELECT COALESCE(SUM(le.change), 0)
                FROM accounts a
                LEFT JOIN account_ledger_entries le
                    ON le.account_id = a.id
                WHERE a.name LIKE 'POTION:%'
            """)
        ).scalar_one()

        new_potions = sum(
            item.quantity
            for item in delivered
        )

        if current_potions + new_potions > 50:
            raise ValueError(
                "Not enough potion capacity"
            )
        if red_used:
            add_ledger_entry(
                connection,
                "Red ML",
                -red_used,
                transaction_id,
            )

        if green_used:
            add_ledger_entry(
                connection,
                "Green ML",
                -green_used,
                transaction_id,
            )

        if blue_used:
            add_ledger_entry(
                connection,
                "Blue ML",
                -blue_used,
                transaction_id,
            )

        for item in delivered:

            # Find the matching recipe SKU.
            recipe = connection.execute(
                sqlalchemy.text("""
                    SELECT sku
                    FROM potions
                    WHERE red = :red
                      AND green = :green
                      AND blue = :blue
                    LIMIT 1
                """),
                {
                    "red": item.potion_type[0],
                    "green": item.potion_type[1],
                    "blue": item.potion_type[2],
                },
            ).first()

            if recipe is None:
                raise ValueError(
                    f"No potion recipe matches {item.potion_type}"
                )

            sku = recipe.sku

            add_ledger_entry(
                connection,
                f"POTION:{sku}",
                item.quantity,
                transaction_id,
            )

        connection.execute(
            sqlalchemy.text("""
                INSERT INTO processed_requests (order_id)
                VALUES (:order_id)
            """),
            {
                "order_id": order_id
            },
        )

def create_bottle_plan(
    red_ml,
    green_ml,
    blue_ml,
    potion_capacity,
):
    plan = []
    recipes = [
        {
            "sku": "RED_POTION_0",
            "red": 100,
            "green": 0,
            "blue": 0,
        },
        {
            "sku": "GREEN_POTION_0",
            "red": 0,
            "green": 100,
            "blue": 0,
        },
        {
            "sku": "BLUE_POTION_0",
            "red": 0,
            "green": 0,
            "blue": 100,
        },
        {
            "sku": "PURPLE_POTION_0",
            "red": 50,
            "green": 0,
            "blue": 50,
        },
        {
            "sku": "BROWN_POTION_0",
            "red": 50,
            "green": 50,
            "blue": 0,
        },
        {
            "sku": "BLACK_POTION_0",
            "red": 33,
            "green": 33,
            "blue": 34,
        },
    ]

    for recipe in recipes:

        red_needed = recipe["red"]
        green_needed = recipe["green"]
        blue_needed = recipe["blue"]

        possible = potion_capacity

        if red_needed:
            possible = min(
                possible,
                red_ml // red_needed,
            )

        if green_needed:
            possible = min(
                possible,
                green_ml // green_needed,
            )

        if blue_needed:
            possible = min(
                possible,
                blue_ml // blue_needed,
            )

        if possible > 0:
            plan.append(
                {
                    "sku": recipe["sku"],
                    "quantity": int(possible),
                }
            )

    return plan

@router.get("/plan")
def bottle_plan():

    with db.engine.begin() as connection:


        red_ml = get_balance(
            connection,
            "Red ML",
        )

        green_ml = get_balance(
            connection,
            "Green ML",
        )

        blue_ml = get_balance(
            connection,
            "Blue ML",
        )

        current_potions = connection.execute(
            sqlalchemy.text("""
                SELECT COALESCE(SUM(le.change), 0)
                FROM accounts a
                LEFT JOIN account_ledger_entries le
                    ON le.account_id = a.id
                WHERE a.name LIKE 'POTION:%'
            """)
        ).scalar_one()
        potion_capacity = max(
            0,
            50 - int(current_potions)
        )

        return create_bottle_plan(
            red_ml=int(red_ml),
            green_ml=int(green_ml),
            blue_ml=int(blue_ml),
            potion_capacity=potion_capacity,
        )