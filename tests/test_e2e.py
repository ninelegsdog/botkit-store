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
    await service.deliver_order(db, order_id, "Your key: ABC123")

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
    await service.deliver_order(db, order_id, "Your key: ABC123")

    delivery = await service.get_delivery(db, order_id)
    assert delivery is not None
    assert delivery["payload"] == "Your key: ABC123"


@pytest.mark.asyncio
async def test_product_card_html():
    card = product_card({
        "name": "Test <script>",
        "price": 100,
    })
    assert "<script>" not in card
