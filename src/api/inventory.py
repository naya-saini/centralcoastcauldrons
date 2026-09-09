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
    red_potions: int
    green_potions: int
    blue_potions: int
    purple_potions: int
    brown_potions: int
    black_potions: int
    red_ml: int
    green_ml: int
    blue_ml: int
    gold: int

class CapacityPlan(BaseModel):
    potion_capacity: int = Field(
        ge=0, le=10, description="Potion capacity units, max 10"
    )
    ml_capacity: int = Field(ge=0, le=10, description="ML capacity units, max 10")

@router.get("/audit", response_model=InventoryAudit)
def get_inventory():

    with db.engine.begin() as connection:

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

        red_potions = connection.execute(
            sqlalchemy.text(
                """
                SELECT COALESCE(SUM(quantity), 0)
                FROM potions
                WHERE red = 100
                  AND green = 0
                  AND blue = 0
                """
            )
        ).scalar_one()

        green_potions = connection.execute(
            sqlalchemy.text(
                """
                SELECT COALESCE(SUM(quantity), 0)
                FROM potions
                WHERE red = 0
                  AND green = 100
                  AND blue = 0
                """
            )
        ).scalar_one()

        blue_potions = connection.execute(
            sqlalchemy.text(
                """
                SELECT COALESCE(SUM(quantity), 0)
                FROM potions
                WHERE red = 0
                  AND green = 0
                  AND blue = 100
                """
            )
        ).scalar_one()

        # Purple = 50% red + 50% blue
        purple_potions = connection.execute(
            sqlalchemy.text(
                """
                SELECT COALESCE(SUM(quantity), 0)
                FROM potions
                WHERE red = 50
                  AND green = 0
                  AND blue = 50
                """
            )
        ).scalar_one()

        brown_potions = connection.execute(
            sqlalchemy.text(
                """
                SELECT COALESCE(SUM(quantity), 0)
                FROM potions
                WHERE red = 50
                  AND green = 50
                  AND blue = 0
                """
            )
        ).scalar_one()

        black_potions = connection.execute(
            sqlalchemy.text(
                """
                SELECT COALESCE(SUM(quantity), 0)
                FROM potions
                WHERE red = 33
                  AND green = 33
                  AND blue = 34
                """
            )
        ).scalar_one()

    return InventoryAudit(
        red_potions=red_potions,
        green_potions=green_potions,
        blue_potions=blue_potions,
        purple_potions=purple_potions,
        brown_potions=brown_potions,
        black_potions=black_potions,
        red_ml=inventory["red_ml"],
        green_ml=inventory["green_ml"],
        blue_ml=inventory["blue_ml"],
        gold=inventory["gold"],
    )

@router.post("/plan", response_model=CapacityPlan)
def get_capacity_plan():
    """
    Provides a daily capacity purchase plan.

    - Start with 1 capacity for 50 potions and 1 capacity for 10,000 ml of potion.
    - Each additional capacity unit costs 1000 gold.
    """
    return CapacityPlan(potion_capacity=0, ml_capacity=0)


@router.post("/deliver/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
def deliver_capacity_plan(capacity_purchase: CapacityPlan, order_id: int):
    """
    Processes the delivery of the planned capacity purchase. order_id is a
    unique value representing a single delivery; the call is idempotent.

    - Start with 1 capacity for 50 potions and 1 capacity for 10,000 ml of potion.
    - Each additional capacity unit costs 1000 gold.
    """
    print(f"capacity delivered: {capacity_purchase} order_id: {order_id}")
    pass
