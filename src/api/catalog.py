from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import List, Annotated
import sqlalchemy
from src import database as db

router = APIRouter()


class CatalogItem(BaseModel):
    sku: Annotated[str, Field(pattern=r"^[a-zA-Z0-9_]{1,20}$")]
    name: str
    quantity: Annotated[int, Field(ge=1, le=10000)]
    price: Annotated[int, Field(ge=1, le=500)]
    potion_type: List[int] = Field(
        ...,
        min_length=4,
        max_length=4,
        description="Must contain exactly 4 elements: [r, g, b, d]",
    )


def create_catalog() -> List[CatalogItem]:
    with db.engine.connect() as connection:
        rows = connection.execute(
            sqlalchemy.text(
                """
                SELECT
                    sku,
                    name,
                    stock,
                    price,
                    red,
                    green,
                    blue,
                    dark
                FROM potion_inventory
                WHERE active AND stock > 0
                ORDER BY stock DESC
                LIMIT 6
                """
            )
        ).mappings().all()

    catalog = []

    for potion in rows:
        catalog.append(
            CatalogItem(
                sku=potion["sku"],
                name=potion["name"],
                quantity=potion["stock"],
                price=potion["price"],
                potion_type=[
                    potion["red"],
                    potion["green"],
                    potion["blue"],
                    potion["dark"],
                ],
            )
        )

    return catalog


@router.get("/catalog/", tags=["catalog"], response_model=List[CatalogItem])
def get_catalog() -> List[CatalogItem]:
    """
    Retrieves the catalog of items. Each unique item combination should have only a single price.
    You can have at most 6 potion SKUs offered in your catalog at one time.
    """
    return create_catalog()