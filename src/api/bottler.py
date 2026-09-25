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
    order_id: str,
):
    """
    Records delivered potions in the ledger.

    The order_id makes the delivery idempotent:
    sending the same order twice will not apply it twice.
    """

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
                "description": f"Bottling delivery {order_id}",
            },
        ).scalar_one()
        total_red_used = 0
        total_green_used = 0
        total_blue_used = 0
        for potion in potions_delivered:

            red = potion.potion_type[0]
            green = potion.potion_type[1]
            blue = potion.potion_type[2]

            potion_row = connection.execute(
                sqlalchemy.text(
                    """
                    SELECT potion_id, sku
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

            if potion_row is None:
                raise ValueError(
                    f"No potion recipe found for "
                    f"red={red}, green={green}, blue={blue}"
                )

            red_ml_used = potion.quantity * red
            green_ml_used = potion.quantity * green
            blue_ml_used = potion.quantity * blue
            total_red_used += red_ml_used
            total_green_used += green_ml_used
            total_blue_used += blue_ml_used

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
                    "change": -red_ml_used,
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
                    "change": -green_ml_used,
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
                    "change": -blue_ml_used,
                },
            )

            potion_account = connection.execute(
                sqlalchemy.text(
                    """
                    SELECT id
                    FROM accounts
                    WHERE name = :name
                    """
                ),
                {
                    "name": potion_row["sku"],
                },
            ).scalar_one_or_none()

            if potion_account is None:
                potion_account = connection.execute(
                    sqlalchemy.text(
                        """
                        INSERT INTO accounts (name)
                        VALUES (:name)
                        RETURNING id
                        """
                    ),
                    {
                        "name": potion_row["sku"],
                    },
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
                    "account_id": potion_account,
                    "transaction_id": transaction_id,
                    "change": potion.quantity,
                },
            )
                    if potions_delivered:
            result = connection.execute(
                sqlalchemy.text("""
                    UPDATE global_inventory
                    SET
                        red_ml = red_ml - :red_used,
                        green_ml = green_ml - :green_used,
                        blue_ml = blue_ml - :blue_used
                    WHERE
                        red_ml >= :red_used
                        AND green_ml >= :green_used
                        AND blue_ml >= :blue_used
                """),
                {
                    "red_used": total_red_used,
                    "green_used": total_green_used,
                    "blue_used": total_blue_used,
                },
            )

            if result.rowcount != 1:
                raise ValueError(
                    "Not enough ML in global inventory "
                    "or inventory row is missing"
                )

                        

        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO processed_requests
                    (order_id, response)
                VALUES
                    (CAST(:order_id AS UUID), :response)
                """
            ),
            {
                "order_id": order_id,
                "response": "{}",
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
                    blue
                FROM potions
                """
            )
        ).mappings().all()

    plan = []
    remaining_capacity = maximum_potion_capacity
    print(f"Maximum potion capacity: {maximum_potion_capacity}")
    print(f"potions: {potions}")
    for potion in potions:
        print(f"Processing potion: {potion}")
        if remaining_capacity <= 0:
            break

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

        red_ml -= amount_to_make * potion["red"]
        green_ml -= amount_to_make * potion["green"]
        blue_ml -= amount_to_make * potion["blue"]

        remaining_capacity -= amount_to_make

    print(f"bottle plan {plan}")
    return plan

@router.post(
    "/plan",
    response_model=List[PotionMixes],
)
def get_bottle_plan():
    """Gets a bottling plan based on global inventory."""

    with db.engine.begin() as connection:
        inventory = connection.execute(
            sqlalchemy.text("""
                SELECT red_ml, green_ml, blue_ml
                FROM global_inventory
            """)
        ).mappings().one()

        current_potions = connection.execute(
            sqlalchemy.text("""
                SELECT COALESCE(SUM(quantity), 0)
                FROM potions
            """)
        ).scalar_one()

        remaining_capacity = max(
            0, 50 - current_potions
        )

        return create_bottle_plan(
            red_ml=inventory["red_ml"],
            green_ml=inventory["green_ml"],
            blue_ml=inventory["blue_ml"],
            maximum_potion_capacity=remaining_capacity,
        )


if __name__ == "__main__":
    print(get_bottle_plan())