from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
import sqlalchemy
from src.api import auth
from enum import Enum
from typing import List, Optional
from uuid import UUID
from src import database as db


router = APIRouter(
    prefix="/carts",
    tags=["cart"],
    dependencies=[Depends(auth.get_api_key)],
)


class SearchSortOptions(str, Enum):
    customer_name = "customer_name"
    item_sku = "item_sku"
    line_item_total = "line_item_total"
    timestamp = "timestamp"


class SearchSortOrder(str, Enum):
    asc = "asc"
    desc = "desc"


class LineItem(BaseModel):
    line_item_id: int
    item_sku: str
    customer_name: str
    line_item_total: int
    timestamp: str


class SearchResponse(BaseModel):
    previous: Optional[str] = None
    next: Optional[str] = None
    results: List[LineItem]


@router.get("/search/", response_model=SearchResponse, tags=["search"])
def search_orders(
    customer_name: str = "",
    potion_sku: str = "",
    search_page: str = "",
    sort_col: SearchSortOptions = SearchSortOptions.timestamp,
    sort_order: SearchSortOrder = SearchSortOrder.desc,
):
    """Search completed order line items by customer name and/or potion SKU."""

    sort_columns = {
        SearchSortOptions.customer_name: "c.customer_name",
        SearchSortOptions.item_sku: "p.sku",
        SearchSortOptions.line_item_total: "(ci.quantity * p.price)",
        SearchSortOptions.timestamp: "c.created_at",
    }

    sort_column = sort_columns[sort_col]
    order = sort_order.value.upper()

    with db.engine.begin() as connection:
        rows = connection.execute(
            sqlalchemy.text(
                f"""
                SELECT
                    ci.cart_item_id AS line_item_id,
                    p.sku AS item_sku,
                    c.customer_name,
                    ci.quantity * p.price AS line_item_total,
                    c.created_at AS timestamp
                FROM cart_items AS ci
                JOIN carts AS c
                    ON ci.cart_id = c.cart_id
                JOIN potions AS p
                    ON ci.potion_id = p.potion_id
                WHERE c.customer_name ILIKE :customer_name
                  AND p.sku ILIKE :potion_sku
                  AND c.status = 'checked_out'
                ORDER BY {sort_column} {order}
                """
            ),
            {
                "customer_name": f"%{customer_name}%",
                "potion_sku": f"%{potion_sku}%",
            },
        ).mappings().all()

    results = []

    for row in rows:
        results.append(
            LineItem(
                line_item_id=row["line_item_id"],
                item_sku=row["item_sku"],
                customer_name=row["customer_name"],
                line_item_total=row["line_item_total"],
                timestamp=row["timestamp"].isoformat(),
            )
        )

    return SearchResponse(
        previous=None,
        next=None,
        results=results,
    )


class Customer(BaseModel):
    customer_id: str
    customer_name: str
    character_class: str
    character_species: str
    level: int = Field(ge=1, le=20)


@router.post("/visits/{visit_id}", status_code=status.HTTP_204_NO_CONTENT)
def post_visits(visit_id: int, customers: List[Customer]):
    print(customers)


class CartCreateResponse(BaseModel):
    cart_id: int


@router.post("/", response_model=CartCreateResponse)
def create_cart(new_cart: Customer):
    """Creates a new cart and stores it in the database."""

    with db.engine.begin() as connection:
        cart_id = connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO carts (
                    customer_id,
                    customer_name,
                    status
                )
                VALUES (
                    :customer_id,
                    :customer_name,
                    'open'
                )
                RETURNING cart_id
                """
            ),
            {
                "customer_id": new_cart.customer_id,
                "customer_name": new_cart.customer_name,
            },
        ).scalar_one()

    return CartCreateResponse(cart_id=cart_id)


class CartItem(BaseModel):
    quantity: int = Field(
        ge=1,
        description="Quantity must be at least 1",
    )


@router.post(
    "/{cart_id}/items/{item_sku}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def set_item_quantity(
    cart_id: int,
    item_sku: str,
    cart_item: CartItem,
):
    """Adds or updates a potion in a cart."""

    with db.engine.begin() as connection:
        cart = connection.execute(
            sqlalchemy.text(
                """
                SELECT cart_id
                FROM carts
                WHERE cart_id = :cart_id
                  AND status = 'open'
                """
            ),
            {"cart_id": cart_id},
        ).first()

        if cart is None:
            raise HTTPException(
                status_code=404,
                detail="Cart not found or already checked out",
            )

        potion = connection.execute(
            sqlalchemy.text(
                """
                SELECT potion_id
                FROM potions
                WHERE sku = :item_sku
                """
            ),
            {"item_sku": item_sku},
        ).first()

        if potion is None:
            raise HTTPException(
                status_code=404,
                detail="Potion not found",
            )

        potion_id = potion[0]

        existing_item = connection.execute(
            sqlalchemy.text(
                """
                SELECT cart_item_id
                FROM cart_items
                WHERE cart_id = :cart_id
                  AND potion_id = :potion_id
                """
            ),
            {
                "cart_id": cart_id,
                "potion_id": potion_id,
            },
        ).first()

        if existing_item:
            connection.execute(
                sqlalchemy.text(
                    """
                    UPDATE cart_items
                    SET quantity = :quantity
                    WHERE cart_id = :cart_id
                      AND potion_id = :potion_id
                    """
                ),
                {
                    "quantity": cart_item.quantity,
                    "cart_id": cart_id,
                    "potion_id": potion_id,
                },
            )
        else:
            connection.execute(
                sqlalchemy.text(
                    """
                    INSERT INTO cart_items (
                        cart_id,
                        potion_id,
                        quantity
                    )
                    VALUES (
                        :cart_id,
                        :potion_id,
                        :quantity
                    )
                    """
                ),
                {
                    "cart_id": cart_id,
                    "potion_id": potion_id,
                    "quantity": cart_item.quantity,
                },
            )


class CheckoutResponse(BaseModel):
    total_potions_bought: int
    total_gold_paid: int


class CartCheckout(BaseModel):
    payment: str
    order_id: UUID


@router.post(
    "/{cart_id}/checkout",
    response_model=CheckoutResponse,
)
def checkout(
    cart_id: int,
    cart_checkout: CartCheckout,
):
    """
    Checks out a cart using ledger balances.

    Inventory is not changed directly. Potion inventory is represented by
    POTION:<sku> ledger accounts, while customer payments are credited to
    the Gold account. A potion_sales row is also written for Version 4
    analytics.
    """

    with db.engine.begin() as connection:

        # Idempotency: return the exact stored response if this order was
        # already successfully processed.
        processed = connection.execute(
            sqlalchemy.text(
                """
                SELECT response
                FROM processed_requests
                WHERE order_id = CAST(:order_id AS UUID)
                """
            ),
            {"order_id": str(cart_checkout.order_id)},
        ).scalar_one_or_none()

        if processed is not None:
            response_data = processed
            if isinstance(response_data, str):
                import json
                response_data = json.loads(response_data)
            return CheckoutResponse(**response_data)

        cart = connection.execute(
            sqlalchemy.text(
                """
                SELECT cart_id, customer_id, customer_name
                FROM carts
                WHERE cart_id = :cart_id
                  AND status = 'open'
                FOR UPDATE
                """
            ),
            {"cart_id": cart_id},
        ).mappings().first()

        if cart is None:
            # If the cart is already checked out, the idempotency record
            # should normally have handled the request.
            raise HTTPException(
                status_code=404,
                detail="Cart not found or already checked out",
            )

        customer = connection.execute(
            sqlalchemy.text(
                """
                SELECT
                    customer_id,
                    customer_name,
                    character_class,
                    character_species,
                    level
                FROM customers
                WHERE customer_id = :customer_id
                """
            ),
            {"customer_id": cart["customer_id"]},
        ).mappings().first()

        if customer is None:
            raise HTTPException(
                status_code=404,
                detail="Customer not found",
            )

        items = connection.execute(
            sqlalchemy.text(
                """
                SELECT
                    ci.quantity,
                    p.potion_id,
                    p.sku,
                    p.price
                FROM cart_items AS ci
                JOIN potions AS p
                    ON ci.potion_id = p.potion_id
                WHERE ci.cart_id = :cart_id
                """
            ),
            {"cart_id": cart_id},
        ).mappings().all()

        if not items:
            raise HTTPException(
                status_code=400,
                detail="Cart is empty",
            )

        total_potions_bought = 0
        total_gold_paid = 0

        # Verify inventory from the ledger, not potions.quantity.
        for item in items:
            inventory_account = f"POTION:{item['sku']}"

            available = connection.execute(
                sqlalchemy.text(
                    """
                    SELECT COALESCE(SUM(le.change), 0)
                    FROM account_ledger_entries AS le
                    JOIN accounts AS a
                      ON a.id = le.account_id
                    WHERE a.name = :account_name
                    """
                ),
                {"account_name": inventory_account},
            ).scalar_one()

            if item["quantity"] > available:
                raise HTTPException(
                    status_code=400,
                    detail=f"Not enough {item['sku']} in inventory. "
                           f"Available: {available}",
                )

            total_potions_bought += item["quantity"]
            total_gold_paid += item["quantity"] * item["price"]

        # Get/create the Gold account.
        gold_account = connection.execute(
            sqlalchemy.text(
                """
                SELECT id
                FROM accounts
                WHERE name = 'Gold'
                FOR UPDATE
                """
            )
        ).scalar_one_or_none()

        if gold_account is None:
            gold_account = connection.execute(
                sqlalchemy.text(
                    """
                    INSERT INTO accounts (name)
                    VALUES ('Gold')
                    RETURNING id
                    """
                )
            ).scalar_one()

        # Create one transaction describing the complete checkout.
        transaction_id = connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO account_transactions (description)
                VALUES (:description)
                RETURNING id
                """
            ),
            {
                "description": f"Potion sale for cart {cart_id}, "
                               f"order {cart_checkout.order_id}"
            },
        ).scalar_one()

        # Credit shop gold.
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
                "account_id": gold_account,
                "transaction_id": transaction_id,
                "change": total_gold_paid,
            },
        )

        # Decrease potion inventory through ledger entries and create the
        # Version 4 sales-event rows.
        for item in items:
            inventory_account = f"POTION:{item['sku']}"

            potion_account = connection.execute(
                sqlalchemy.text(
                    """
                    SELECT id
                    FROM accounts
                    WHERE name = :account_name
                    FOR UPDATE
                    """
                ),
                {"account_name": inventory_account},
            ).scalar_one_or_none()

            if potion_account is None:
                raise HTTPException(
                    status_code=500,
                    detail=f"Ledger account missing for {item['sku']}",
                )

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
                    "change": -item["quantity"],
                },
            )

            connection.execute(
                sqlalchemy.text(
                    """
                    INSERT INTO potion_sales (
                        potion_sku,
                        quantity,
                        unit_price,
                        customer_id,
                        customer_class,
                        character_species,
                        level
                    )
                    VALUES (
                        :potion_sku,
                        :quantity,
                        :unit_price,
                        :customer_id,
                        :customer_class,
                        :character_species,
                        :level
                    )
                    """
                ),
                {
                    "potion_sku": item["sku"],
                    "quantity": item["quantity"],
                    "unit_price": item["price"],
                    "customer_id": customer["customer_id"],
                    "customer_class": customer["character_class"],
                    "character_species": customer["character_species"],
                    "level": customer["level"],
                },
            )

        response_data = {
            "total_potions_bought": total_potions_bought,
            "total_gold_paid": total_gold_paid,
        }

        # Store the response so the same order_id returns the same result.
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO processed_requests (order_id, response)
                VALUES (
                    CAST(:order_id AS UUID),
                    CAST(:response AS JSONB)
                )
                """
            ),
            {
                "order_id": str(cart_checkout.order_id),
                "response": __import__("json").dumps(response_data),
            },
        )

        connection.execute(
            sqlalchemy.text(
                """
                UPDATE carts
                SET status = 'checked_out'
                WHERE cart_id = :cart_id
                """
            ),
            {"cart_id": cart_id},
        )

    return CheckoutResponse(**response_data)
