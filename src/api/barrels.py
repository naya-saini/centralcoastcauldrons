from dataclasses import dataclass
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field, field_validator
from typing import List

import random
import sqlalchemy
from src.api import auth
from src import database as db

router = APIRouter(
    prefix="/barrels",
    tags=["barrels"],
    dependencies=[Depends(auth.get_api_key)],
)

ml_colors = ["red", "green", "blue", "dark"]


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
def post_deliver_barrels(barrels_delivered: List[Barrel], order_id: int):
    """
    Processes barrels delivered based on the provided order_id. order_id is a unique value representing
    a single delivery; the call is idempotent based on the order_id.
    """
    print(f"barrels delivered: {barrels_delivered} order_id: {order_id}")

    delivery = calculate_barrel_summary(barrels_delivered)

    changes = {"gold": -delivery.gold_paid}
    for barrel in barrels_delivered:
        for i, fraction in enumerate(barrel.potion_type):
            if fraction == 0:
                continue
            key = f"{ml_colors[i]}_ml"
            changes[key] = changes.get(key, 0) + int(
                barrel.ml_per_barrel * fraction * barrel.quantity
            )

    with db.engine.begin() as connection:
        # idempotency: claim this order_id
        result = connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO processed_requests (endpoint, order_id)
                VALUES ('barrels_deliver', :order_id)
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
            {"description": f"barrel delivery order {order_id}"},
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


def create_barrel_plan(
    gold: int,
    max_barrel_capacity: int,
    current_red_ml: int,
    current_green_ml: int,
    current_blue_ml: int,
    current_dark_ml: int,
    wholesale_catalog: List[Barrel],
    current_potions: dict = None,
) -> List[BarrelOrder]:
    print(
        f"gold: {gold}, max_barrel_capacity: {max_barrel_capacity}, "
        f"potions: {current_potions}, wholesale_catalog: {wholesale_catalog}"
    )
    current_potions = current_potions or {}

    # randomly pick red, green, or blue
    color = random.choice(["red", "green", "blue"])
    color_index = ml_colors.index(color)

    # need fewer than 5 potions of that color
    if current_potions.get(color, 0) >= 5:
        return []

    # small barrel of that color
    small_barrel = next(
        (
            b
            for b in wholesale_catalog
            if "SMALL" in b.sku.upper() and b.potion_type[color_index] == 1
        ),
        None,
    )

    # need to afford it
    if small_barrel and small_barrel.price <= gold:
        return [BarrelOrder(sku=small_barrel.sku, quantity=1)]

    return []


@router.post("/plan", response_model=List[BarrelOrder])
def get_wholesale_purchase_plan(wholesale_catalog: List[Barrel]):
    """
    Gets the plan for purchasing wholesale barrels. Read-only: no database writes.
    """
    print(f"barrel catalog: {wholesale_catalog}")

    with db.engine.connect() as connection:
        rows = connection.execute(
            sqlalchemy.text("SELECT item, balance FROM inventory_balances")
        ).all()
    balances = {r.item: r.balance for r in rows}

    return create_barrel_plan(
        gold=balances.get("gold", 0),
        max_barrel_capacity=10000,
        current_red_ml=balances.get("red_ml", 0),
        current_green_ml=balances.get("green_ml", 0),
        current_blue_ml=balances.get("blue_ml", 0),
        current_dark_ml=balances.get("dark_ml", 0),
        wholesale_catalog=wholesale_catalog,
        current_potions={
            "red": balances.get("potion:red", 0),
            "green": balances.get("potion:green", 0),
            "blue": balances.get("potion:blue", 0),
        },
    )