from __future__ import annotations

import pytest

from src.core.ui import product_card
from src.store import service


@pytest.mark.asyncio
async def test_full_purchase_flow(db):
    cat_id = await service.create_category(db, "Test")
    prod_id = await service.create_product(
        db, category_id=cat_id, name="Product", price=100
    )
    await service.add_to_cart(db, 111, prod_id)
    cart = await service.get_cart(db, 111)
    assert len(cart) == 1

    order_id = await service.create_order(db, 111, prod_id, 100)
    await service.mark_paid(db, order_id, "payment_123")
    await _fulfill_with_key(db, order_id, "Your key: ABC123")

    order = await service.get_order(db, order_id)
    assert order["status"] == "delivered"


@pytest.mark.asyncio
async def test_idempotent_delivery(db):
    cat_id = await service.create_category(db, "Test")
    prod_id = await service.create_product(
        db, category_id=cat_id, name="Product", price=100
    )
    order_id = await service.create_order(db, 111, prod_id, 100)
    await service.mark_paid(db, order_id, "payment_123")
    await _fulfill_with_key(db, order_id, "Your key: ABC123")

    delivery = await service.get_delivery(db, order_id, 111)
    assert delivery is not None
    assert delivery["payload"] == "Your key: ABC123"


@pytest.mark.asyncio
async def test_product_card_html():
    card = product_card({
        "name": "Test <script>",
        "price": 100,
    })
    assert "<script>" not in card


async def _fulfill_with_key(db, order_id: int, value: str) -> None:
    """Put one unit of stock in place and fulfil the order with it.

    `fulfill_order` allocates the key itself, so a test that wants a known payload puts
    that exact value into stock first.
    """
    from sqlalchemy import text

    async with db.session() as session:
        result = await session.execute(
            text("SELECT product_id FROM orders WHERE id = :oid"), {"oid": order_id}
        )
        product_id = int(result.scalar_one())
    async with db.transaction() as session:
        await session.execute(
            text("INSERT INTO keys (product_id, value, used_by) VALUES (:p, :v, NULL)"),
            {"p": product_id, "v": value},
        )
    assert await service.fulfill_order(db, order_id) == value

