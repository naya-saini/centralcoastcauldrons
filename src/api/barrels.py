from dataclasses import dataclass
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field, field_validator
from typing import List

import sqlalchemy
from src.api import auth
from src import database as db

router = APIRouter(
    prefix="/barrels",
    tags=["barrels"],
    dependencies=[Depends(auth.get_api_key)],
)


class Barrel(BaseModel):
    sku: str
    ml_per_barrel: int = Field(gt=0, description="Must be greater than 0")
    potion_type: List[float] = Field(
        ...,
        min_length=4,
        max_length=4,
        description="Must contain exactly 4 elements: [r, g, b, d] that sum to 1.0",
    )
    price: int = Field(ge=0, description="Price must be non-negative")
    quantity: int = Field(ge=0, description="Quantity must be non-negative")

    @field_validator("potion_type")
    @classmethod
    def validate_potion_type(cls, potion_type: List[float]) -> List[float]:
        if len(potion_type) != 4:
            raise ValueError("potion_type must have exactly 4 elements: [r, g, b, d]")
        if not abs(sum(potion_type) - 1.0) < 1e-6:
            raise ValueError("Sum of potion_type values must be exactly 1.0")
        return potion_type


class BarrelOrder(BaseModel):
    sku: str
    quantity: int = Field(gt=0, description="Quantity must be greater than 0")


@dataclass
class BarrelSummary:
    gold_paid: int


def calculate_barrel_summary(barrels: List[Barrel]) -> BarrelSummary:
    return BarrelSummary(gold_paid=sum(b.price * b.quantity for b in barrels))


@router.post("/deliver/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
def post_deliver_barrels(
    barrels_delivered: List[Barrel],
    order_id: str,
):
    """
    Records a barrel delivery in the ledger.

    The order_id makes the delivery idempotent:
    sending the same order twice will not apply it twice.
    """

    delivery = calculate_barrel_summary(barrels_delivered)

    red_ml = 0
    green_ml = 0
    blue_ml = 0

    for barrel in barrels_delivered:
        if barrel.potion_type == [1, 0, 0, 0]:
            red_ml += barrel.ml_per_barrel * barrel.quantity

        elif barrel.potion_type == [0, 1, 0, 0]:
            green_ml += barrel.ml_per_barrel * barrel.quantity

        elif barrel.potion_type == [0, 0, 1, 0]:
            blue_ml += barrel.ml_per_barrel * barrel.quantity

    with db.engine.begin() as connection:

        existing = connection.execute(
            sqlalchemy.text(
                """
                SELECT order_id
                FROM processed_requests
                WHERE order_id = CAST(:order_id AS UUID)
                """
            ),
            {"order_id": order_id},
        ).first()

        if existing is not None:
            return

        transaction_id = connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO account_transactions (description)
                VALUES (:description)
                RETURNING id
                """
            ),
            {
                "description": f"Barrel delivery {order_id}",
            },
        ).scalar_one()

        gold_account = connection.execute(
            sqlalchemy.text(
                """
                SELECT id
                FROM accounts
                WHERE name = 'Gold'
                """
            )
        ).scalar_one_or_none()

        if gold_account is None:
            gold_account = connection.execute(
                sqlalchemy.text(
                    """
                    INSERT INTO accounts (name)
                    VALUES ('Gold')
                    RETURNING id
                    """
                )
            ).scalar_one()

        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO account_ledger_entries
                    (account_id, account_transaction_id, change)
                VALUES
                    (:account_id, :transaction_id, :change)
                """
            ),
            {
                "account_id": gold_account,
                "transaction_id": transaction_id,
                "change": -delivery.gold_paid,
            },
        )

        red_account = connection.execute(
            sqlalchemy.text(
                """
                SELECT id
                FROM accounts
                WHERE name = 'Red ML'
                """
            )
        ).scalar_one_or_none()

        if red_account is None:
            red_account = connection.execute(
                sqlalchemy.text(
                    """
                    INSERT INTO accounts (name)
                    VALUES ('Red ML')
                    RETURNING id
                    """
                )
            ).scalar_one()

        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO account_ledger_entries
                    (account_id, account_transaction_id, change)
                VALUES
                    (:account_id, :transaction_id, :change)
                """
            ),
            {
                "account_id": red_account,
                "transaction_id": transaction_id,
                "change": red_ml,
            },
        )
        green_account = connection.execute(
            sqlalchemy.text(
                """
                SELECT id
                FROM accounts
                WHERE name = 'Green ML'
                """
            )
        ).scalar_one_or_none()

        if green_account is None:
            green_account = connection.execute(
                sqlalchemy.text(
                    """
                    INSERT INTO accounts (name)
                    VALUES ('Green ML')
                    RETURNING id
                    """
                )
            ).scalar_one()

        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO account_ledger_entries
                    (account_id, account_transaction_id, change)
                VALUES
                    (:account_id, :transaction_id, :change)
                """
            ),
            {
                "account_id": green_account,
                "transaction_id": transaction_id,
                "change": green_ml,
            },
        )

        blue_account = connection.execute(
            sqlalchemy.text(
                """
                SELECT id
                FROM accounts
                WHERE name = 'Blue ML'
                """
            )
        ).scalar_one_or_none()

        if blue_account is None:
            blue_account = connection.execute(
                sqlalchemy.text(
                    """
                    INSERT INTO accounts (name)
                    VALUES ('Blue ML')
                    RETURNING id
                    """
                )
            ).scalar_one()

        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO account_ledger_entries
                    (account_id, account_transaction_id, change)
                VALUES
                    (:account_id, :transaction_id, :change)
                """
            ),
            {
                "account_id": blue_account,
                "transaction_id": transaction_id,
                "change": blue_ml,
            },
        )
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO processed_requests
                    (order_id, response)
                VALUES(CAST(:order_id AS UUID), :response)
                """
            ),{
                "order_id":order_id,
                "response": "{}",
            },
        )


import random

def create_barrel_plan(
    gold: int,
    max_barrel_capacity: int,
    current_red_ml: int,
    current_green_ml: int,
    current_blue_ml: int,
    wholesale_catalog: List[Barrel],
    potion_counts,
) -> List[BarrelOrder]:

    GOLD_RESERVE = 50
    MIN_POTIONS = 10

    color_index = {
        "red": 0,
        "green": 1,
        "blue": 2,
    }

    orders = []
    available_gold = gold - GOLD_RESERVE

    for color, potion_info in potion_counts.items():

        count = potion_info["quantity"]

        if count >= MIN_POTIONS:
            continue

        possible_barrels = [
            barrel
            for barrel in wholesale_catalog
            if barrel.potion_type[color_index[color]] == 1
            and barrel.price <= available_gold
        ]

        if not possible_barrels:
            continue

        best_barrel = min(
            possible_barrels,
            key=lambda barrel: barrel.price / barrel.ml_per_barrel,
        )

        orders.append(
            BarrelOrder(
                sku=best_barrel.sku,
                quantity=1,
            )
        )

        available_gold -= best_barrel.price

    return orders

@router.post("/plan", response_model=List[BarrelOrder])
def get_wholesale_purchase_plan():
    """
    Creates a barrel purchase plan based on current
    inventory and the wholesale barrel catalog.
    """
    wholesale_catalog = [
        Barrel(
            sku="RED_BARREL",
            ml_per_barrel=1000,
            potion_type=[1, 0, 0, 0],
            price=100,
            quantity=1,
        ),
        Barrel(
            sku="GREEN_BARREL",
            ml_per_barrel=1000,
            potion_type=[0, 1, 0, 0],
            price=100,
            quantity=1,
        ),
        Barrel(
            sku="BLUE_BARREL",
            ml_per_barrel=1000,
            potion_type=[0, 0, 1, 0],
            price=100,
            quantity=1,
        ),
    ]

    with db.engine.begin() as connection:

        inventory = connection.execute(
            sqlalchemy.text(
                """
                SELECT
                    COALESCE(SUM(
                        CASE
                            WHEN a.name = 'Gold'
                            THEN ale.change
                            ELSE 0
                        END
                    ), 0) AS gold,

                    COALESCE(SUM(
                        CASE
                            WHEN a.name = 'Red ML'
                            THEN ale.change
                            ELSE 0
                        END
                    ), 0) AS red_ml,

                    COALESCE(SUM(
                        CASE
                            WHEN a.name = 'Green ML'
                            THEN ale.change
                            ELSE 0
                        END
                    ), 0) AS green_ml,

                    COALESCE(SUM(
                        CASE
                            WHEN a.name = 'Blue ML'
                            THEN ale.change
                            ELSE 0
                        END
                    ), 0) AS blue_ml

                FROM accounts a
                LEFT JOIN account_ledger_entries ale
                    ON a.id = ale.account_id
                """
            )
        ).mappings().one()

        potions = connection.execute(
            sqlalchemy.text(
                """
                SELECT
                    sku,
                    quantity,
                    red,
                    green,
                    blue
                FROM potions
                """
            )
        ).mappings().all()

    potion_inventory = {
        potion["sku"]: {
            "quantity": potion["quantity"],
            "composition": [
                potion["red"] / 100,
                potion["green"] / 100,
                potion["blue"] / 100,
                0,
            ],
        }
        for potion in potions
    }

    return create_barrel_plan(
        gold=inventory["gold"],
        max_barrel_capacity=10000,
        current_red_ml=inventory["red_ml"],
        current_green_ml=inventory["green_ml"],
        current_blue_ml=inventory["blue_ml"],
        wholesale_catalog=wholesale_catalog,
        potion_counts=potion_inventory,
    )