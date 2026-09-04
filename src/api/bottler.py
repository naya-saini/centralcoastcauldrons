from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field, field_validator
from typing import List
from src.api import auth
from src import database as db
import sqlalchemy


router = APIRouter(
    prefix="/bottler",
    tags=["bottler"],
    dependencies=[Depends(auth.get_api_key)],
)


class PotionMixes(BaseModel):
    potion_type: List[int] = Field(
        ...,
        min_length=4,
        max_length=4,
        description="Must contain exactly 4 elements: [r, g, b, d]",
    )

    quantity: int = Field(
        ...,
        ge=1,
        le=10000,
        description="Quantity must be between 1 and 10,000",
    )

    @field_validator("potion_type")
    @classmethod
    def validate_potion_type(cls, potion_type: List[int]) -> List[int]:
        if sum(potion_type) != 100:
            raise ValueError(
                "Sum of potion_type values must be exactly 100"
            )
        return potion_type


@router.post(
    "/deliver/{order_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def post_deliver_bottles(
    potions_delivered: List[PotionMixes],
    order_id: int,
):
    """
    Record delivered potions in the database.
    """

    with db.engine.begin() as connection:

        for potion in potions_delivered:

            red = potion.potion_type[0]
            green = potion.potion_type[1]
            blue = potion.potion_type[2]

            # Find the matching potion in the database
            potion_row = connection.execute(
                sqlalchemy.text(
                    """
                    SELECT
                        potion_id,
                        sku
                    FROM potions
                    WHERE red = :red
                      AND green = :green
                      AND blue = :blue
                    """
                ),
                {
                    "red": red,
                    "green": green,
                    "blue": blue,
                },
            ).mappings().first()

            # If the potion type does not exist,
            # we cannot add it to inventory.
            if potion_row is None:
                continue

            # Calculate how many ml were used
            red_ml_used = potion.quantity * red
            green_ml_used = potion.quantity * green
            blue_ml_used = potion.quantity * blue

            # Remove ingredients
            connection.execute(
                sqlalchemy.text(
                    """
                    UPDATE global_inventory
                    SET
                        red_ml = red_ml - :red_ml_used,
                        green_ml = green_ml - :green_ml_used,
                        blue_ml = blue_ml - :blue_ml_used
                    """
                ),
                {
                    "red_ml_used": red_ml_used,
                    "green_ml_used": green_ml_used,
                    "blue_ml_used": blue_ml_used,
                },
            )

            # Add finished potions to inventory
            connection.execute(
                sqlalchemy.text(
                    """
                    UPDATE potions
                    SET quantity = quantity + :quantity
                    WHERE potion_id = :potion_id
                    """
                ),
                {
                    "quantity": potion.quantity,
                    "potion_id": potion_row["potion_id"],
                },
            )


def create_bottle_plan(
    red_ml: int,
    green_ml: int,
    blue_ml: int,
    maximum_potion_capacity: int,
) -> List[PotionMixes]:

    with db.engine.begin() as connection:
        potions = connection.execute(
            sqlalchemy.text(
                """
                SELECT
                    red,
                    green,
                    blue,
                    quantity
                FROM potions
                """
            )
        ).mappings().all()

    plan = []

    remaining_capacity = maximum_potion_capacity

    for potion in potions:

        if remaining_capacity <= 0:
            break

        # Calculate how many of this potion can be made
        possible_amounts = []

        if potion["red"] > 0:
            possible_amounts.append(
                red_ml // potion["red"]
            )

        if potion["green"] > 0:
            possible_amounts.append(
                green_ml // potion["green"]
            )

        if potion["blue"] > 0:
            possible_amounts.append(
                blue_ml // potion["blue"]
            )

        # If no potion can be made, skip it
        if not possible_amounts:
            continue

        amount_to_make = min(
            min(possible_amounts),
            remaining_capacity,
        )

        if amount_to_make <= 0:
            continue

        plan.append(
            PotionMixes(
                potion_type=[
                    potion["red"],
                    potion["green"],
                    potion["blue"],
                    0,
                ],
                quantity=amount_to_make,
            )
        )

        # Reserve the ingredients for this plan
        red_ml -= amount_to_make * potion["red"]
        green_ml -= amount_to_make * potion["green"]
        blue_ml -=amount_to_make * potion["blue"]

        remaining_capacity -= amount_to_make

    return plan


@router.post(
    "/plan",
    response_model=List[PotionMixes],
)
def get_bottle_plan():
    """
    Gets a bottling plan based on potion recipes
    stored in the database.
    """

    with db.engine.begin() as connection:
        row = connection.execute(
            sqlalchemy.text(
                """
                SELECT
                    red_ml,
                    green_ml,
                    blue_ml
                FROM global_inventory
                """
            )).mappings().one()

    return create_bottle_plan(
        red_ml=row["red_ml"],
        green_ml=row["green_ml"],
        blue_ml=row["blue_ml"],
        maximum_potion_capacity = 50,
    )


if __name__ == "__main__":
    print(get_bottle_plan())