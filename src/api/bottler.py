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

def potion_item(potion_type: List[int]) -> str:
    """Ledger item name for a potion. Pure colors get 'potion:red' etc.,
    which is what the barrels plan reads. Mixes get 'potion:r_g_b_d'."""
    for i, color in enumerate(ml_colors[:3]):
        if potion_type[i] == 100:
            return f"potion:{color}"
    return "potion:" + "_".join(str(x) for x in potion_type)

@router.post("/deliver/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
def post_deliver_bottles(potions_delivered: List[PotionMixes], order_id: int):
    """
    Delivery of potions requested after plan. order_id is a unique value representing
    a single delivery; the call is idempotent based on the order_id.
    """
    print(f"potions delivered: {potions_delivered} order_id: {order_id}")

    changes = {}
    for mix in potions_delivered:
        for i, pct in enumerate(mix.potion_type):
            if pct == 0:
                continue
            key = f"{ml_colors[i]}_ml"
            changes[key] = changes.get(key, 0) - pct * mix.quantity

        item = potion_item(mix.potion_type)
        changes[item] = changes.get(item, 0) + mix.quantity

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
) -> List[PotionMixes]:
    plan = []

    for potion_type, ml in (
        ([100, 0, 0, 0], red_ml),
        ([0, 100, 0, 0], green_ml),
        ([0, 0, 100, 0], blue_ml),
    ):
        quantity = ml // 100
        if quantity >= 1:
            plan.append(PotionMixes(potion_type=potion_type, quantity=min(quantity, 10000)))

    return plan



@router.post("/plan", response_model=List[PotionMixes])
def get_bottle_plan():
    """
    Gets the plan for bottling potions.
    Each bottle has a quantity of what proportion of red, green, blue, and dark potions to add.
    Colors are expressed in integers from 0 to 100 that must sum up to exactly 100.
    """
    with db.engine.connect() as connection:
        rows = connection.execute(
            sqlalchemy.text("SELECT item, balance FROM inventory_balances")
        ).all()
    balances = {r.item: r.balance for r in rows}

    return create_bottle_plan(
        red_ml=balances.get("red_ml", 0),
        green_ml=balances.get("green_ml", 0),
        blue_ml=balances.get("blue_ml", 0),
        dark_ml=balances.get("dark_ml", 0),
        maximum_potion_capacity=50,
        current_potion_inventory=[],
    )


if __name__ == "__main__":
    print(get_bottle_plan())