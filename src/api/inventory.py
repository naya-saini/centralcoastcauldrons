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
        description="Potion capacity units, max 10",
    )
    ml_capacity: int = Field(
        ge=0,
        le=10,
        description="ML capacity units, max 10",
    )


def get_ledger_balance(connection, account_name: str) -> int:
    """
    Returns the current balance of an account.

    Balance is calculated from all ledger entries:
        SUM(account_ledger_entries.change)
    """

    balance = connection.execute(
        sqlalchemy.text(
            """
            SELECT
                COALESCE(SUM(le.change), 0)
            FROM accounts a
            LEFT JOIN account_ledger_entries le
                ON le.account_id = a.id
            WHERE a.name = :account_name
            """
        ),
        {
            "account_name": account_name,
        },
    ).scalar_one()

    return int(balance)


@router.get("/audit", response_model=InventoryAudit)
def get_inventory():
    """
    Returns the current inventory from the ledger.

    number_of_potions = total finished potions
    ml_in_barrels = total raw potion ingredients
    gold = current gold

    The ledger is the source of truth.
    """

    with db.engine.begin() as connection:

        gold = get_ledger_balance(
            connection,
            "Gold",
        )

        red_ml = get_ledger_balance(
            connection,
            "Red ML",
        )

        green_ml = get_ledger_balance(
            connection,
            "Green ML",
        )

        blue_ml = get_ledger_balance(
            connection,
            "Blue ML",
        )
        potion_result = connection.execute(
            sqlalchemy.text(
                """
                SELECT
                    COALESCE(SUM(le.change), 0)
                FROM accounts a
                LEFT JOIN account_ledger_entries le
                    ON le.account_id = a.id
                WHERE a.name LIKE 'POTION:%'
                """
            )
        ).scalar_one()

        number_of_potions = int(potion_result)
    ml_in_barrels = (
        red_ml
        + green_ml
        + blue_ml
    )

    return InventoryAudit(
        number_of_potions=number_of_potions,
        ml_in_barrels=ml_in_barrels,
        gold=gold,
    )


@router.post(
    "/plan",
    response_model=CapacityPlan,
)
def get_capacity_plan():
    """
    Provides a daily capacity purchase plan.

    - Start with 1 capacity for 50 potions
    - Start with 1 capacity for 10,000 ML
    - Each additional capacity unit costs 1000 gold
    """

    return CapacityPlan(
        potion_capacity=0,
        ml_capacity=0,
    )


@router.post(
    "/deliver/{order_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def deliver_capacity_plan(
    capacity_purchase: CapacityPlan,
    order_id: str,
):
    """
    Processes the delivery of the planned capacity purchase.

    Capacity purchasing is not currently represented as an
    inventory account in the ledger, so there is no inventory
    balance to update here yet.
    """

    print(
        f"capacity delivered: {capacity_purchase} "
        f"order_id: {order_id}"
    )

    pass