"""State-dependent view tests for the store bot.

These tests assert that service-layer views return *different, correct* results
depending on the underlying state (empty vs populated, active vs inactive, etc.),
so a view cannot silently return the same answer for every state.

Pattern to replicate in other bots: for each state dimension, set up the state,
call the view/service, and assert the shape/content differs between states.
"""

from __future__ import annotations

import pytest

from src.store import service


@pytest.mark.asyncio
async def test_cart_view_empty_vs_populated(db):
    """Empty cart and populated cart must differ."""
    empty = await service.get_cart(db, user_id=42)
    assert empty == []

    cat_id = await service.create_category(db, "Cat")
    prod_id = await service.create_product(db, category_id=cat_id, name="P", price=10)
    await service.add_to_cart(db, 42, prod_id)

    populated = await service.get_cart(db, 42)
    assert len(populated) == 1
    assert populated != empty
    assert populated[0]["name"] == "P"


@pytest.mark.asyncio
async def test_products_view_active_vs_inactive(db):
    """Inactive products must not appear in the active-products view."""
    cat_id = await service.create_category(db, "Cat")
    await service.create_product(db, category_id=cat_id, name="Active", price=10)
    inactive_id = await service.create_product(db, category_id=cat_id, name="Inactive", price=10)

    # Mark the second product inactive directly
    async with db.transaction() as session:
        from sqlalchemy import text
        await session.execute(
            text("UPDATE products SET is_active = 0 WHERE id = :id"),
            {"id": inactive_id},
        )

    products = await service.get_products(db, cat_id)
    names = [p["name"] for p in products]
    assert "Active" in names
    assert "Inactive" not in names


@pytest.mark.asyncio
async def test_categories_view_empty_vs_populated(db):
    """Empty categories list vs populated must differ."""
    assert await service.get_categories(db) == []

    await service.create_category(db, "Cat 1")
    cats = await service.get_categories(db)
    assert len(cats) == 1
    assert cats[0]["name"] == "Cat 1"


@pytest.mark.asyncio
async def test_get_product_missing_vs_present(db):
    """Missing product returns None, present product returns a dict."""
    assert await service.get_product(db, 99999) is None

    cat_id = await service.create_category(db, "Cat")
    prod_id = await service.create_product(db, category_id=cat_id, name="P", price=10)
    product = await service.get_product(db, prod_id)
    assert product is not None
    assert product["name"] == "P"


@pytest.mark.asyncio
async def test_cart_duplicate_increments_qty(db):
    """Adding the same product twice must increment qty, not create a duplicate row."""
    cat_id = await service.create_category(db, "Cat")
    prod_id = await service.create_product(db, category_id=cat_id, name="P", price=10)
    await service.add_to_cart(db, 7, prod_id)
    await service.add_to_cart(db, 7, prod_id)
    cart = await service.get_cart(db, 7)
    assert len(cart) == 1
    assert cart[0]["qty"] == 2
