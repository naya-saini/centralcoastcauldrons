from fastapi import APIRouter, Depends, status
import sqlalchemy
from src.api import auth
from src import database as db

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(auth.get_api_key)],
)


@router.post("/reset", status_code=status.HTTP_204_NO_CONTENT)
def reset():
    """
    Gold back to 100, everything else back to 0, carts cleared.
    The potions table (your catalog of recipes) is kept.
    """
    with db.engine.begin() as connection:
        # children before parents because of foreign keys
        for table in [
            "potion_sales",
            "cart_items",
            "carts",
            "customers",
            "ledger_entries",
            "inventory_transactions",
            "processed_requests",
        ]:
            connection.execute(sqlalchemy.text(f"DELETE FROM {table}"))

        tx_id = connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO inventory_transactions (description)
                VALUES ('reset: starting gold')
                RETURNING id
                """
            )
        ).scalar_one()

        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO ledger_entries (transaction_id, item, change)
                VALUES (:tx, 'gold', 100)
                """
            ),
            {"tx": tx_id},
        )