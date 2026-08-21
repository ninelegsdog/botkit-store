from __future__ import annotations

import pytest

from src.store import service


@pytest.mark.asyncio
async def test_create_category(db):
    cat_id = await service.create_category(db, "Test Category")
    assert cat_id > 0


@pytest.mark.asyncio
async def test_get_categories(db):
    await service.create_category(db, "Cat 1")
    await service.create_category(db, "Cat 2")
    cats = await service.get_categories(db)
    assert len(cats) == 2


@pytest.mark.asyncio
async def test_create_product(db):
    cat_id = await service.create_category(db, "Test")
    prod_id = await service.create_product(
        db, category_id=cat_id, name="Product", price=100
    )
    assert prod_id > 0


@pytest.mark.asyncio
async def test_get_product(db):
    cat_id = await service.create_category(db, "Test")
    prod_id = await service.create_product(
        db, category_id=cat_id, name="Product", price=100
    )
    product = await service.get_product(db, prod_id)
    assert product is not None
    assert product["name"] == "Product"


@pytest.mark.asyncio
async def test_add_to_cart(db):
    cat_id = await service.create_category(db, "Test")
    prod_id = await service.create_product(
        db, category_id=cat_id, name="Product", price=100
    )
    await service.add_to_cart(db, 123, prod_id)
    cart = await service.get_cart(db, 123)
    assert len(cart) == 1


@pytest.mark.asyncio
async def test_add_to_cart_duplicate(db):
    cat_id = await service.create_category(db, "Test")
    prod_id = await service.create_product(
        db, category_id=cat_id, name="Product", price=100
    )
    await service.add_to_cart(db, 123, prod_id)
    await service.add_to_cart(db, 123, prod_id)
    cart = await service.get_cart(db, 123)
    assert len(cart) == 1
    assert cart[0]["qty"] == 2


@pytest.mark.asyncio
async def test_remove_from_cart(db):
    cat_id = await service.create_category(db, "Test")
    prod_id = await service.create_product(
        db, category_id=cat_id, name="Product", price=100
    )
    await service.add_to_cart(db, 123, prod_id)
    await service.remove_from_cart(db, 123, prod_id)
    cart = await service.get_cart(db, 123)
    assert len(cart) == 0


@pytest.mark.asyncio
async def test_create_order(db):
    cat_id = await service.create_category(db, "Test")
    prod_id = await service.create_product(
        db, category_id=cat_id, name="Product", price=100
    )
    order_id = await service.create_order(db, 123, prod_id, 100)
    assert order_id > 0


@pytest.mark.asyncio
async def test_get_user_orders(db):
    cat_id = await service.create_category(db, "Test")
    prod_id = await service.create_product(
        db, category_id=cat_id, name="Product", price=100
    )
    await service.create_order(db, 123, prod_id, 100)
    orders = await service.get_user_orders(db, 123)
    assert len(orders) == 1
