from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
import sqlalchemy
from src.api import auth
from src import database as db


router = APIRouter(
    prefix="/inventory",
    tags=["inventory"],
    dependencies=[Depends(auth.get_api_key)],
)


class InventoryAudit(BaseModel):
    number_of_potions: int
    ml_in_barrels: int
    gold: int


class CapacityPlan(BaseModel):
    potion_capacity: int = Field(
        ge=0,
        le=10,
        description="Potion capacity units, max 10"
    )
    ml_capacity: int = Field(
        ge=0,
        le=10,
        description="ML capacity units, max 10"
    )


@router.get("/audit", response_model=InventoryAudit)
def get_inventory():
    """
    Returns the current inventory.

    number_of_potions = total finished potions
    ml_in_barrels = total raw potion ingredients
    gold = current gold
    """

    with db.engine.connect() as connection:
        rows = connection.execute(
            sqlalchemy.text("SELECT item, balance FROM inventory_balances")
        ).all()

    balances = {r.item: r.balance for r in rows}

    ml_in_barrels = sum(
        balance for item, balance in balances.items() if item.endswith("_ml")
    )

    number_of_potions = sum(
        balance for item, balance in balances.items() if item.startswith("potion:")
    )

    return InventoryAudit(
        number_of_potions=number_of_potions,
        ml_in_barrels=ml_in_barrels,
        gold=balances.get("gold", 0),
    )


@router.post("/plan", response_model=CapacityPlan)
def get_capacity_plan():
    """
    Provides a daily capacity purchase plan.

    - Start with 1 capacity for 50 potions
    - Start with 1 capacity for 10,000 ML
    - Each additional capacity unit costs 1000 gold
    """

    return CapacityPlan(
        potion_capacity=2,
        ml_capacity=2,
    )


@router.post(
    "/deliver/{order_id}",
    status_code=status.HTTP_204_NO_CONTENT
)
def deliver_capacity_plan(
    capacity_purchase: CapacityPlan,
    order_id: int
):
    """
    Processes the delivery of the planned capacity purchase.
    """

    print(
        f"capacity delivered: {capacity_purchase} "
        f"order_id: {order_id}"
    )

    gold_cost = 1000 * (
        capacity_purchase.potion_capacity + capacity_purchase.ml_capacity
    )

    changes = {
        "gold": -gold_cost,
        "potion_capacity": capacity_purchase.potion_capacity,
        "ml_capacity": capacity_purchase.ml_capacity,
    }

    with db.engine.begin() as connection:
        result = connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO processed_requests (endpoint, order_id)
                VALUES ('capacity_deliver', :order_id)
                ON CONFLICT (endpoint, order_id) DO NOTHING
                """
            ),
            {"order_id": order_id},
        )
        if result.rowcount == 0:
            return

        tx_id = connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO inventory_transactions (description)
                VALUES (:description)
                RETURNING id
                """
            ),
            {"description": f"capacity delivery order {order_id}"},
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