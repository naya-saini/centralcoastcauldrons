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

    with db.engine.begin() as connection:

        # Get gold and raw ML
        inventory = connection.execute(
            sqlalchemy.text(
                """
                SELECT
                    red_ml,
                    green_ml,
                    blue_ml,
                    gold
                FROM global_inventory
                """
            )
        ).mappings().one()

        # Get total number of finished potions
        number_of_potions = connection.execute(
            sqlalchemy.text(
                """
                SELECT COALESCE(SUM(quantity), 0)
                FROM potions
                """
            )
        ).scalar_one()

    # Total ML currently stored as raw ingredients
    ml_in_barrels = (
        inventory["red_ml"]
        + inventory["green_ml"]
        + inventory["blue_ml"]
    )

    return InventoryAudit(
        number_of_potions=number_of_potions,
        ml_in_barrels=ml_in_barrels,
        gold=inventory["gold"],
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
        potion_capacity=0,
        ml_capacity=0,
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

    pass