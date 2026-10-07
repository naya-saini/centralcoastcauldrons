from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
import sqlalchemy
import json
from src.api import auth
from enum import Enum
from typing import List, Optional
from src import database as db

router = APIRouter(
    prefix="/carts",
    tags=["cart"],
    dependencies=[Depends(auth.get_api_key)],
)

PAGE_SIZE = 5


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


SORT_COLUMNS = {
    "customer_name": "c.name",
    "item_sku": "p.sku",
    "line_item_total": "(ps.quantity * ps.unit_price)",
    "timestamp": "ps.sold_at",
}


@router.get("/search/", response_model=SearchResponse, tags=["search"])
def search_orders(
    customer_name: str = "",
    potion_sku: str = "",
    search_page: str = "",
    sort_col: SearchSortOptions = SearchSortOptions.timestamp,
    sort_order: SearchSortOrder = SearchSortOrder.desc,
):
    """
    Search sales line items by customer name and/or potion sku.
    """
    try:
        offset = max(int(search_page), 0) if search_page else 0
    except ValueError:
        offset = 0

    # column and direction come from whitelists (enums), never from raw input
    order_by = f"{SORT_COLUMNS[sort_col.value]} {sort_order.value}, ps.id"

    with db.engine.connect() as connection:
        rows = connection.execute(
            sqlalchemy.text(
                f"""
                SELECT ps.id AS line_item_id, p.sku AS item_sku, c.name AS customer_name,
                       ps.quantity * ps.unit_price AS line_item_total, ps.sold_at
                FROM potion_sales ps
                JOIN potions p ON p.id = ps.potion_id
                JOIN customers c ON c.id = ps.customer_id
                WHERE c.name ILIKE :cust AND p.sku ILIKE :sku
                ORDER BY {order_by}
                LIMIT :limit OFFSET :offset
                """
            ),
            {
                "cust": f"%{customer_name}%",
                "sku": f"%{potion_sku}%",
                "limit": PAGE_SIZE + 1,
                "offset": offset,
            },
        ).all()

    return SearchResponse(
        previous=str(max(offset - PAGE_SIZE, 0)) if offset > 0 else None,
        next=str(offset + PAGE_SIZE) if len(rows) > PAGE_SIZE else None,
        results=[
            LineItem(
                line_item_id=r.line_item_id,
                item_sku=r.item_sku,
                customer_name=r.customer_name,
                line_item_total=r.line_item_total,
                timestamp=r.sold_at.isoformat(),
            )
            for r in rows[:PAGE_SIZE]
        ],
    )


class Customer(BaseModel):
    customer_id: str
    customer_name: str
    character_class: str
    character_species: str
    level: int = Field(ge=1, le=20)


def upsert_customer(connection, c: Customer) -> int:
    return connection.execute(
        sqlalchemy.text(
            """
            INSERT INTO customers (external_id, name, class, species, level)
            VALUES (:eid, :name, :cls, :species, :level)
            ON CONFLICT (external_id) DO UPDATE
              SET name = EXCLUDED.name, class = EXCLUDED.class,
                  species = EXCLUDED.species, level = EXCLUDED.level
            RETURNING id
            """
        ),
        {
            "eid": c.customer_id,
            "name": c.customer_name,
            "cls": c.character_class,
            "species": c.character_species,
            "level": c.level,
        },
    ).scalar_one()


@router.post("/visits/{visit_id}", status_code=status.HTTP_204_NO_CONTENT)
def post_visits(visit_id: int, customers: List[Customer]):
    """
    Shares the customers that visited the store on that tick.
    """
    with db.engine.begin() as connection:
        for c in customers:
            upsert_customer(connection, c)


class CartCreateResponse(BaseModel):
    cart_id: int


@router.post("/", response_model=CartCreateResponse)
def create_cart(new_cart: Customer):
    """
    Creates a new cart for a specific customer.
    """
    with db.engine.begin() as connection:
        customer_id = upsert_customer(connection, new_cart)
        cart_id = connection.execute(
            sqlalchemy.text("INSERT INTO carts (customer_id) VALUES (:c) RETURNING id"),
            {"c": customer_id},
        ).scalar_one()
    return CartCreateResponse(cart_id=cart_id)


class CartItem(BaseModel):
    quantity: int = Field(ge=1, description="Quantity must be at least 1")


@router.post("/{cart_id}/items/{item_sku}", status_code=status.HTTP_204_NO_CONTENT)
def set_item_quantity(cart_id: int, item_sku: str, cart_item: CartItem):
    with db.engine.begin() as connection:
        cart = connection.execute(
            sqlalchemy.text("SELECT 1 FROM carts WHERE id = :id"), {"id": cart_id}
        ).first()
        potion = connection.execute(
            sqlalchemy.text("SELECT id FROM potions WHERE sku = :sku AND active"),
            {"sku": item_sku},
        ).first()
        if not cart or not potion:
            raise HTTPException(status_code=404, detail="Cart or potion not found")

        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO cart_items (cart_id, potion_id, quantity)
                VALUES (:cart, :potion, :q)
                ON CONFLICT (cart_id, potion_id) DO UPDATE SET quantity = :q
                """
            ),
            {"cart": cart_id, "potion": potion.id, "q": cart_item.quantity},
        )


class CheckoutResponse(BaseModel):
    total_potions_bought: int
    total_gold_paid: int


class CartCheckout(BaseModel):
    payment: str


@router.post("/{cart_id}/checkout", response_model=CheckoutResponse)
def checkout(cart_id: int, cart_checkout: CartCheckout):
    """
    Handles checkout. Idempotent on cart_id: retries get the stored response.
    """
    with db.engine.begin() as connection:
        claimed = connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO processed_requests (endpoint, order_id)
                VALUES ('cart_checkout', :id)
                ON CONFLICT (endpoint, order_id) DO NOTHING
                """
            ),
            {"id": cart_id},
        )
        if claimed.rowcount == 0:
            stored = connection.execute(
                sqlalchemy.text(
                    """
                    SELECT response FROM processed_requests
                    WHERE endpoint = 'cart_checkout' AND order_id = :id
                    """
                ),
                {"id": cart_id},
            ).scalar_one()
            return CheckoutResponse(**stored)

        cart = connection.execute(
            sqlalchemy.text("SELECT customer_id FROM carts WHERE id = :id"),
            {"id": cart_id},
        ).first()
        if not cart:
            raise HTTPException(status_code=404, detail="Cart not found")

        lines = connection.execute(
            sqlalchemy.text(
                """
                SELECT ci.potion_id, ci.quantity, p.sku, p.price, pi.stock
                FROM cart_items ci
                JOIN potions p ON p.id = ci.potion_id
                JOIN potion_inventory pi ON pi.id = p.id
                WHERE ci.cart_id = :id
                """
            ),
            {"id": cart_id},
        ).all()

        for l in lines:
            if l.stock < l.quantity:
                raise HTTPException(status_code=400, detail=f"Not enough {l.sku}")

        total_potions = sum(l.quantity for l in lines)
        total_gold = sum(l.quantity * l.price for l in lines)

        if lines:
            tx_id = connection.execute(
                sqlalchemy.text(
                    """
                    INSERT INTO inventory_transactions (description)
                    VALUES (:d) RETURNING id
                    """
                ),
                {"d": f"checkout cart {cart_id}"},
            ).scalar_one()

            # gold up, each potion down, one ledger transaction
            entries = [{"tx": tx_id, "item": "gold", "change": total_gold}]
            entries += [
                {"tx": tx_id, "item": f"potion:{l.sku}", "change": -l.quantity}
                for l in lines
            ]
            connection.execute(
                sqlalchemy.text(
                    """
                    INSERT INTO ledger_entries (transaction_id, item, change)
                    VALUES (:tx, :item, :change)
                    """
                ),
                [e for e in entries if e["change"] != 0],
            )

            # instrumentation: who bought what, and when
            for l in lines:
                connection.execute(
                    sqlalchemy.text(
                        """
                        INSERT INTO potion_sales
                          (transaction_id, cart_id, customer_id, potion_id, quantity,
                           unit_price, day_of_week, hour_of_day)
                        VALUES (:tx, :cart, :cust, :potion, :q, :price,
                                trim(to_char(now(), 'Day')),
                                extract(hour from now()))
                        """
                    ),
                    {
                        "tx": tx_id,
                        "cart": cart_id,
                        "cust": cart.customer_id,
                        "potion": l.potion_id,
                        "q": l.quantity,
                        "price": l.price,
                    },
                )

        response = {
            "total_potions_bought": total_potions,
            "total_gold_paid": total_gold,
        }
        connection.execute(
            sqlalchemy.text(
                """
                UPDATE processed_requests SET response = CAST(:r AS jsonb)
                WHERE endpoint = 'cart_checkout' AND order_id = :id
                """
            ),
            {"r": json.dumps(response), "id": cart_id},
        )

    return CheckoutResponse(**response)