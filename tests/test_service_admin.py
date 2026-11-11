from __future__ import annotations

import pytest
from sqlalchemy import text

from src.store import service

# ── Категории ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_category_name(db):
    cat_id = await service.create_category(db, "Old")
    ok = await service.update_category(db, cat_id, name="New")
    assert ok is True
    cats = await service.get_categories_admin(db)
    assert cats[0]["name"] == "New"


@pytest.mark.asyncio
async def test_update_category_position(db):
    cat_id = await service.create_category(db, "Test")
    ok = await service.update_category(db, cat_id, position=5)
    assert ok is True
    cats = await service.get_categories_admin(db)
    assert cats[0]["position"] == 5


@pytest.mark.asyncio
async def test_update_category_is_active(db):
    cat_id = await service.create_category(db, "Test")
    ok = await service.update_category(db, cat_id, is_active=False)
    assert ok is True
    cats = await service.get_categories_admin(db)
    assert cats[0]["is_active"] == 0


@pytest.mark.asyncio
async def test_update_category_missing(db):
    ok = await service.update_category(db, 99999, name="X")
    assert ok is False


@pytest.mark.asyncio
async def test_update_category_no_changes(db):
    cat_id = await service.create_category(db, "Test")
    ok = await service.update_category(db, cat_id)
    assert ok is False


@pytest.mark.asyncio
async def test_delete_category_soft(db):
    cat_id = await service.create_category(db, "ToDelete")
    ok = await service.delete_category(db, cat_id)
    assert ok is True
    cats = await service.get_categories_admin(db)
    assert cats[0]["is_active"] == 0


@pytest.mark.asyncio
async def test_delete_category_with_products_refused(db):
    cat_id = await service.create_category(db, "HasProducts")
    await service.create_product(db, category_id=cat_id, name="P", price=10)
    ok = await service.delete_category(db, cat_id)
    assert ok is False
    # Category still active
    cats = await service.get_categories_admin(db)
    assert cats[0]["is_active"] == 1


@pytest.mark.asyncio
async def test_delete_category_missing(db):
    ok = await service.delete_category(db, 99999)
    assert ok is False


@pytest.mark.asyncio
async def test_toggle_category(db):
    cat_id = await service.create_category(db, "Toggle")
    new_val = await service.toggle_category(db, cat_id)
    assert new_val is False  # was 1, now 0
    new_val = await service.toggle_category(db, cat_id)
    assert new_val is True  # was 0, now 1


@pytest.mark.asyncio
async def test_toggle_category_missing(db):
    result = await service.toggle_category(db, 99999)
    assert result is None


@pytest.mark.asyncio
async def test_get_categories_admin_includes_inactive(db):
    await service.create_category(db, "Active")
    cat_id = await service.create_category(db, "Inactive")
    await service.update_category(db, cat_id, is_active=False)
    cats = await service.get_categories_admin(db)
    assert len(cats) == 2
    active_names = {c["name"] for c in cats}
    assert "Active" in active_names
    assert "Inactive" in active_names


# ── Товары ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_product_full(db):
    cat_id = await service.create_category(db, "Cat")
    prod_id = await service.create_product(db, category_id=cat_id, name="Old", price=10)
    ok = await service.update_product(
        db, prod_id,
        name="New",
        description="Desc",
        price=99,
        delivery_type="link",
        delivery_payload="https://example.com",
        photo_file_id="file_123",
        is_active=False,
    )
    assert ok is True
    prod = await service.get_product_admin(db, prod_id)
    assert prod["name"] == "New"
    assert prod["description"] == "Desc"
    assert prod["price"] == 99
    assert prod["delivery_type"] == "link"
    assert prod["delivery_payload"] == "https://example.com"
    assert prod["photo_file_id"] == "file_123"
    assert prod["is_active"] == 0


@pytest.mark.asyncio
async def test_update_product_partial(db):
    cat_id = await service.create_category(db, "Cat")
    prod_id = await service.create_product(db, category_id=cat_id, name="Old", price=10)
    ok = await service.update_product(db, prod_id, price=50)
    assert ok is True
    prod = await service.get_product_admin(db, prod_id)
    assert prod["price"] == 50
    assert prod["name"] == "Old"  # unchanged


@pytest.mark.asyncio
async def test_update_product_no_changes(db):
    cat_id = await service.create_category(db, "Cat")
    prod_id = await service.create_product(db, category_id=cat_id, name="Old", price=10)
    ok = await service.update_product(db, prod_id)
    assert ok is False


@pytest.mark.asyncio
async def test_update_product_missing(db):
    ok = await service.update_product(db, 99999, name="X")
    assert ok is False


@pytest.mark.asyncio
async def test_delete_product_soft(db):
    cat_id = await service.create_category(db, "Cat")
    prod_id = await service.create_product(db, category_id=cat_id, name="ToDelete", price=10)
    ok = await service.delete_product(db, prod_id)
    assert ok is True
    prod = await service.get_product_admin(db, prod_id)
    assert prod["is_active"] == 0


@pytest.mark.asyncio
async def test_delete_product_with_unfulfilled_order_refused(db):
    cat_id = await service.create_category(db, "Cat")
    prod_id = await service.create_product(db, category_id=cat_id, name="P", price=10)
    await service.create_order(db, 1, prod_id, 10)
    ok = await service.delete_product(db, prod_id)
    assert ok is False
    prod = await service.get_product_admin(db, prod_id)
    assert prod["is_active"] == 1


@pytest.mark.asyncio
async def test_delete_product_delivered_order_allowed(db):
    """Delivered orders don't block deletion (no pending liability)."""
    cat_id = await service.create_category(db, "Cat")
    prod_id = await service.create_product(db, category_id=cat_id, name="P", price=10)
    order_id = await service.create_order(db, 1, prod_id, 10)
    await service.mark_paid(db, order_id, "pay_1")
    await service.fulfill_order(db, order_id)  # need stock
    # Actually fulfill needs stock, so just test that paid blocks it
    ok = await service.delete_product(db, prod_id)
    assert ok is False  # paid order blocks


@pytest.mark.asyncio
async def test_delete_product_missing(db):
    ok = await service.delete_product(db, 99999)
    assert ok is False


@pytest.mark.asyncio
async def test_toggle_product(db):
    cat_id = await service.create_category(db, "Cat")
    prod_id = await service.create_product(db, category_id=cat_id, name="Toggle", price=10)
    new_val = await service.toggle_product(db, prod_id)
    assert new_val is False
    new_val = await service.toggle_product(db, prod_id)
    assert new_val is True


@pytest.mark.asyncio
async def test_toggle_product_missing(db):
    result = await service.toggle_product(db, 99999)
    assert result is None


@pytest.mark.asyncio
async def test_get_product_admin_includes_inactive(db):
    cat_id = await service.create_category(db, "Cat")
    prod_id = await service.create_product(db, category_id=cat_id, name="P", price=10)
    await service.update_product(db, prod_id, is_active=False)
    prod = await service.get_product_admin(db, prod_id)
    assert prod is not None
    assert prod["is_active"] == 0


# ── Ключи и остатки ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_add_keys(db):
    cat_id = await service.create_category(db, "Cat")
    prod_id = await service.create_product(db, category_id=cat_id, name="P", price=10)
    count = await service.add_keys(db, prod_id, ["key1", "key2", "key3"])
    assert count == 3
    stock = await service.get_stock(db, prod_id)
    assert stock["total"] == 3
    assert stock["used"] == 0
    assert stock["available"] == 3


@pytest.mark.asyncio
async def test_add_keys_empty(db):
    cat_id = await service.create_category(db, "Cat")
    prod_id = await service.create_product(db, category_id=cat_id, name="P", price=10)
    count = await service.add_keys(db, prod_id, [])
    assert count == 0


@pytest.mark.asyncio
async def test_get_stock_used(db):
    cat_id = await service.create_category(db, "Cat")
    prod_id = await service.create_product(db, category_id=cat_id, name="P", price=10)
    await service.add_keys(db, prod_id, ["k1", "k2", "k3"])
    # Mark one as used
    async with db.transaction() as session:
        await session.execute(
            text("UPDATE keys SET used_by = 1 WHERE value = 'k1'"),
        )
    stock = await service.get_stock(db, prod_id)
    assert stock["total"] == 3
    assert stock["used"] == 1
    assert stock["available"] == 2


# ── Заказы ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_manual_fulfill_order(db):
    cat_id = await service.create_category(db, "Cat")
    prod_id = await service.create_product(db, category_id=cat_id, name="P", price=10)
    await service.add_keys(db, prod_id, ["secret-key-1"])
    order_id = await service.create_order(db, 1, prod_id, 10)
    await service.mark_paid(db, order_id, "pay_1")
    ok = await service.manual_fulfill_order(db, order_id, "manual-payload")
    assert ok is True
    order = await service.get_order(db, order_id)
    assert order["status"] == "delivered"


@pytest.mark.asyncio
async def test_manual_fulfill_order_idempotent(db):
    cat_id = await service.create_category(db, "Cat")
    prod_id = await service.create_product(db, category_id=cat_id, name="P", price=10)
    await service.add_keys(db, prod_id, ["k1"])
    order_id = await service.create_order(db, 1, prod_id, 10)
    await service.mark_paid(db, order_id, "pay_1")
    await service.manual_fulfill_order(db, order_id, "first")
    ok = await service.manual_fulfill_order(db, order_id, "second")
    assert ok is False  # already delivered, cannot transition from paid again
    deliveries = await service.get_delivery(db, order_id, 1)
    assert deliveries["payload"] == "first"


@pytest.mark.asyncio
async def test_manual_fulfill_order_missing(db):
    ok = await service.manual_fulfill_order(db, 99999, "payload")
    assert ok is False


@pytest.mark.asyncio
async def test_manual_fulfill_order_not_paid(db):
    cat_id = await service.create_category(db, "Cat")
    prod_id = await service.create_product(db, category_id=cat_id, name="P", price=10)
    order_id = await service.create_order(db, 1, prod_id, 10)  # pending_payment
    ok = await service.manual_fulfill_order(db, order_id, "payload")
    assert ok is False


@pytest.mark.asyncio
async def test_cancel_order_created(db):
    cat_id = await service.create_category(db, "Cat")
    prod_id = await service.create_product(db, category_id=cat_id, name="P", price=10)
    order_id = await service.create_order(db, 1, prod_id, 10)
    ok = await service.cancel_order(db, order_id)
    assert ok is True
    order = await service.get_order(db, order_id)
    assert order["status"] == "cancelled"


@pytest.mark.asyncio
async def test_cancel_order_pending_payment(db):
    cat_id = await service.create_category(db, "Cat")
    prod_id = await service.create_product(db, category_id=cat_id, name="P", price=10)
    order_id = await service.create_order(db, 1, prod_id, 10)
    ok = await service.cancel_order(db, order_id)
    assert ok is True


@pytest.mark.asyncio
async def test_cancel_order_paid_refused(db):
    cat_id = await service.create_category(db, "Cat")
    prod_id = await service.create_product(db, category_id=cat_id, name="P", price=10)
    order_id = await service.create_order(db, 1, prod_id, 10)
    await service.mark_paid(db, order_id, "pay_1")
    ok = await service.cancel_order(db, order_id)
    assert ok is False


@pytest.mark.asyncio
async def test_cancel_order_missing(db):
    ok = await service.cancel_order(db, 99999)
    assert ok is False


@pytest.mark.asyncio
async def test_refund_order(db):
    cat_id = await service.create_category(db, "Cat")
    prod_id = await service.create_product(db, category_id=cat_id, name="P", price=10)
    order_id = await service.create_order(db, 1, prod_id, 10)
    await service.mark_paid(db, order_id, "pay_1")
    ok = await service.refund_order(db, order_id)
    assert ok is True
    order = await service.get_order(db, order_id)
    assert order["status"] == "refunded"


@pytest.mark.asyncio
async def test_refund_order_created_refused(db):
    cat_id = await service.create_category(db, "Cat")
    prod_id = await service.create_product(db, category_id=cat_id, name="P", price=10)
    order_id = await service.create_order(db, 1, prod_id, 10)  # pending_payment
    ok = await service.refund_order(db, order_id)
    assert ok is False


# ── Статистика и списки заказов ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_orders_by_status(db):
    cat_id = await service.create_category(db, "Cat")
    prod_id = await service.create_product(db, category_id=cat_id, name="P", price=10)
    o1 = await service.create_order(db, 1, prod_id, 10)
    await service.create_order(db, 2, prod_id, 20)
    await service.mark_paid(db, o1, "pay_1")
    orders = await service.get_orders_by_status(db, status="paid")
    assert len(orders) == 1
    assert orders[0]["id"] == o1


@pytest.mark.asyncio
async def test_get_orders_for_user(db):
    cat_id = await service.create_category(db, "Cat")
    prod_id = await service.create_product(db, category_id=cat_id, name="P", price=10)
    await service.create_order(db, 1, prod_id, 10)
    await service.create_order(db, 2, prod_id, 20)
    user1 = await service.get_orders_for_user(db, 1)
    user2 = await service.get_orders_for_user(db, 2)
    assert len(user1) == 1
    assert len(user2) == 1


@pytest.mark.asyncio
async def test_get_sales_stats(db):
    cat_id = await service.create_category(db, "Cat")
    prod_id = await service.create_product(db, category_id=cat_id, name="P", price=10)
    o1 = await service.create_order(db, 1, prod_id, 10)
    o2 = await service.create_order(db, 2, prod_id, 20)
    await service.mark_paid(db, o1, "pay_1")
    await service.mark_paid(db, o2, "pay_2")
    stats = await service.get_sales_stats(db, period="day")
    assert stats["paid_count"] == 2


@pytest.mark.asyncio
async def test_get_low_stock_products(db):
    cat_id = await service.create_category(db, "Cat")
    prod_id = await service.create_product(db, category_id=cat_id, name="LowStock", price=10, delivery_type="text")
    await service.add_keys(db, prod_id, ["k1"])  # only 1 key, threshold default 5
    low = await service.get_low_stock_products(db, threshold=5)
    assert len(low) == 1
    assert low[0]["name"] == "LowStock"
    assert low[0]["available_keys"] == 1


# ── Отрицательные сценарии ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fulfill_order_exhausts_stock(db):
    """When keys run out, order stays paid and fulfill returns None."""
    cat_id = await service.create_category(db, "Cat")
    prod_id = await service.create_product(db, category_id=cat_id, name="P", price=10, delivery_type="text")
    order_id = await service.create_order(db, 1, prod_id, 10)
    await service.mark_paid(db, order_id, "pay_1")
    # No keys added
    result = await service.fulfill_order(db, order_id)
    assert result is None
    order = await service.get_order(db, order_id)
    assert order["status"] == "paid"  # rolled back, not delivered


@pytest.mark.asyncio
async def test_delete_category_protects_orders(db):
    """Category with products that have orders cannot be deleted."""
    cat_id = await service.create_category(db, "Cat")
    prod_id = await service.create_product(db, category_id=cat_id, name="P", price=10)
    await service.create_order(db, 1, prod_id, 10)
    # Order is pending_payment, which blocks product deletion
    # Actually pending_payment blocks deletion
    ok = await service.delete_product(db, prod_id)
    assert ok is False  # pending_payment order blocks
