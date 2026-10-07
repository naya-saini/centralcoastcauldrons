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

ml_colors = ["red", "green", "blue", "dark"]


class PotionMixes(BaseModel):
    potion_type: List[int] = Field(
        ...,
        min_length=4,
        max_length=4,
        description="Must contain exactly 4 elements: [r, g, b, d]",
    )
    quantity: int = Field(
        ..., ge=1, le=10000, description="Quantity must be between 1 and 10,000"
    )

    @field_validator("potion_type")
    @classmethod
    def validate_potion_type(cls, potion_type: List[int]) -> List[int]:
        if sum(potion_type) != 100:
            raise ValueError("Sum of potion_type values must be exactly 100")
        return potion_type


def get_or_create_potion_sku(connection, potion_type: List[int]) -> str:
    """Find the potions row for this mix, creating it if it's a new recipe."""
    r, g, b, d = potion_type
    connection.execute(
        sqlalchemy.text(
            """
            INSERT INTO potions (sku, name, red, green, blue, dark)
            VALUES (:sku, :sku, :r, :g, :b, :d)
            ON CONFLICT (red, green, blue, dark) DO NOTHING
            """
        ),
        {"sku": f"potion_{r}_{g}_{b}_{d}", "r": r, "g": g, "b": b, "d": d},
    )
    return connection.execute(
        sqlalchemy.text(
            "SELECT sku FROM potions WHERE red=:r AND green=:g AND blue=:b AND dark=:d"
        ),
        {"r": r, "g": g, "b": b, "d": d},
    ).scalar_one()


@router.post("/deliver/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
def post_deliver_bottles(potions_delivered: List[PotionMixes], order_id: int):
    """
    Delivery of potions requested after plan. Idempotent on order_id.
    """
    print(f"potions delivered: {potions_delivered} order_id: {order_id}")

    with db.engine.begin() as connection:
        result = connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO processed_requests (endpoint, order_id)
                VALUES ('bottler_deliver', :order_id)
                ON CONFLICT (endpoint, order_id) DO NOTHING
                """
            ),
            {"order_id": order_id},
        )
        if result.rowcount == 0:
            return  # already processed

        # ml used goes down, potions made go up
        changes = {}
        for mix in potions_delivered:
            for i, pct in enumerate(mix.potion_type):
                if pct:
                    key = f"{ml_colors[i]}_ml"
                    changes[key] = changes.get(key, 0) - pct * mix.quantity
            sku = get_or_create_potion_sku(connection, mix.potion_type)
            item = f"potion:{sku}"
            changes[item] = changes.get(item, 0) + mix.quantity

        tx_id = connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO inventory_transactions (description)
                VALUES (:description)
                RETURNING id
                """
            ),
            {"description": f"bottle delivery order {order_id}"},
        ).scalar_one()

        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO ledger_entries (transaction_id, item, change)
                VALUES (:tx, :item, :change)
                """
            ),
            [
                {"tx": tx_id, "item": item, "change": change}
                for item, change in changes.items()
                if change != 0
            ],
        )


def create_bottle_plan(
    red_ml: int,
    green_ml: int,
    blue_ml: int,
    dark_ml: int,
    maximum_potion_capacity: int,
    current_potion_inventory: List[PotionMixes],
    recipes: List[List[int]] = None,
) -> List[PotionMixes]:
    ml = [red_ml, green_ml, blue_ml, dark_ml]
    room = maximum_potion_capacity - sum(p.quantity for p in current_potion_inventory)
    made = {}

    # round-robin over every recipe in the potions table so none hogs the ml
    progress = True
    while room > 0 and progress:
        progress = False
        for recipe in recipes or []:
            if room > 0 and all(ml[i] >= recipe[i] for i in range(4)):
                for i in range(4):
                    ml[i] -= recipe[i]
                made[tuple(recipe)] = made.get(tuple(recipe), 0) + 1
                room -= 1
                progress = True

    return [PotionMixes(potion_type=list(k), quantity=v) for k, v in made.items()]


@router.post("/plan", response_model=List[PotionMixes])
def get_bottle_plan():
    """
    Read-only: no database writes.
    """
    with db.engine.connect() as connection:
        balances = {
            r.item: r.balance
            for r in connection.execute(
                sqlalchemy.text("SELECT item, balance FROM inventory_balances")
            ).all()
        }
        potions = connection.execute(
            sqlalchemy.text(
                "SELECT red, green, blue, dark, stock FROM potion_inventory WHERE active"
            )
        ).all()

    stocked = [
        PotionMixes(potion_type=[p.red, p.green, p.blue, p.dark], quantity=p.stock)
        for p in potions
        if p.stock > 0
    ]
    return create_bottle_plan(
        red_ml=balances.get("red_ml", 0),
        green_ml=balances.get("green_ml", 0),
        blue_ml=balances.get("blue_ml", 0),
        dark_ml=balances.get("dark_ml", 0),
        maximum_potion_capacity=50,
        current_potion_inventory=stocked,
        recipes=[[p.red, p.green, p.blue, p.dark] for p in potions],
    )