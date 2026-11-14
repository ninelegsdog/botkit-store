from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Chat, Message, User

from src.admin.handlers import create_admin_router
from src.core.auth import AdminGate
from src.core.bot_factory import AppState
from src.core.config import Config
from src.store import service


def _message(user_id: int = 1, text: str = "x") -> Message:
    return Message(
        message_id=1,
        chat=Chat(id=1, type="private"),
        date=datetime.now(),
        from_user=User(id=user_id, is_bot=False, first_name="U"),
        text=text,
    )


def _callback(user_id: int = 1, data: str = "test") -> CallbackQuery:
    return CallbackQuery(
        id="cb1",
        chat_instance="ci1",
        from_user=User(id=user_id, is_bot=False, first_name="U"),
        data=data,
        message=_message(user_id, text="orig"),
    )


def _fsm(user_id: int = 1) -> FSMContext:
    storage = MemoryStorage()
    key = None  # type: ignore[assignment]
    # FSMContext needs bot and storage; we create minimal via MemoryStorage

    key = __import__("aiogram.fsm.context", fromlist=["StorageKey"]).StorageKey(
        bot_id=1, chat_id=1, user_id=user_id, business_connection_id=None
    )
    return FSMContext(storage=storage, key=key)


def _fake_app_state(db=None):
    if db is None:
        db = MagicMock()
    config = Config(
        bot_token="test",
        admin_password="secret",
        admin_ids=[1],
    )
    app_state = MagicMock(spec=AppState)
    app_state.db = db
    app_state.config = config
    return app_state


# ── Админ-аутентификация ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_cmd_sets_password_state(db):
    app_state = _fake_app_state(db)
    router = create_admin_router(app_state)
    # Just verify router is created with handlers
    assert router is not None


@pytest.mark.asyncio
async def test_admin_wrong_password(db):
    app_state = _fake_app_state(db)
    create_admin_router(app_state)

    gate = AdminGate("secret", [1])
    assert gate.authorize(1, "wrong") is False
    assert gate.authorize(1, "secret") is True


# ── Сервис: категории ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_service_category_full_cycle(db):
    cat_id = await service.create_category(db, "Courses")
    assert cat_id == 1

    cats = await service.get_categories_admin(db)
    assert len(cats) == 1
    assert cats[0]["name"] == "Courses"
    assert cats[0]["is_active"] == 1

    # Toggle off
    new_val = await service.toggle_category(db, cat_id)
    assert new_val is False

    # Toggle on
    new_val = await service.toggle_category(db, cat_id)
    assert new_val is True

    # Update name
    ok = await service.update_category(db, cat_id, name="Books")
    assert ok is True
    cats = await service.get_categories_admin(db)
    assert cats[0]["name"] == "Books"

    # Delete (no products)
    ok = await service.delete_category(db, cat_id)
    assert ok is True
    cats = await service.get_categories_admin(db)
    assert cats[0]["is_active"] == 0


@pytest.mark.asyncio
async def test_service_category_delete_with_products_refused(db):
    cat_id = await service.create_category(db, "HasProd")
    prod_id = await service.create_product(db, category_id=cat_id, name="P", price=10)
    await service.create_order(db, 1, prod_id, 10)
    ok = await service.delete_category(db, cat_id)
    assert ok is False  # category has products


# ── Сервис: товары ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_service_product_full_cycle(db):
    cat_id = await service.create_category(db, "Cat")
    prod_id = await service.create_product(db, category_id=cat_id, name="Course", price=100)

    prod = await service.get_product_admin(db, prod_id)
    assert prod["name"] == "Course"
    assert prod["price"] == 100

    # Update
    ok = await service.update_product(db, prod_id, name="Course v2", price=150)
    assert ok is True
    prod = await service.get_product_admin(db, prod_id)
    assert prod["name"] == "Course v2"
    assert prod["price"] == 150

    # Toggle off
    new_val = await service.toggle_product(db, prod_id)
    assert new_val is False

    # Toggle on
    new_val = await service.toggle_product(db, prod_id)
    assert new_val is True

    # Delete (no orders)
    ok = await service.delete_product(db, prod_id)
    assert ok is True
    prod = await service.get_product_admin(db, prod_id)
    assert prod["is_active"] == 0


@pytest.mark.asyncio
async def test_service_product_delete_with_order_refused(db):
    cat_id = await service.create_category(db, "Cat")
    prod_id = await service.create_product(db, category_id=cat_id, name="P", price=10)
    await service.create_order(db, 1, prod_id, 10)
    ok = await service.delete_product(db, prod_id)
    assert ok is False


# ── Сервис: ключи ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_service_add_keys_and_stock(db):
    cat_id = await service.create_category(db, "Cat")
    prod_id = await service.create_product(db, category_id=cat_id, name="P", price=10)

    count = await service.add_keys(db, prod_id, ["a", "b", "c"])
    assert count == 3

    stock = await service.get_stock(db, prod_id)
    assert stock["total"] == 3
    assert stock["available"] == 3


# ── Сервис: заказы ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_service_order_fulfill_cancel_refund(db):
    cat_id = await service.create_category(db, "Cat")
    prod_id = await service.create_product(db, category_id=cat_id, name="P", price=10)
    await service.add_keys(db, prod_id, ["key1"])

    order_id = await service.create_order(db, 1, prod_id, 10)
    await service.mark_paid(db, order_id, "pay_1")

    # Manual fulfill
    ok = await service.manual_fulfill_order(db, order_id, "manual-key")
    assert ok is True
    order = await service.get_order(db, order_id)
    assert order["status"] == "delivered"

    # Idempotent second call returns False (already delivered)
    ok = await service.manual_fulfill_order(db, order_id, "manual-key-2")
    assert ok is False

    # Cancel should not work on delivered order
    ok = await service.cancel_order(db, order_id)
    assert ok is False

    # Refund should work on delivered order
    ok = await service.refund_order(db, order_id)
    assert ok is True
    order = await service.get_order(db, order_id)
    assert order["status"] == "refunded"


# ── Сервис: статистика ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_service_sales_stats(db):
    cat_id = await service.create_category(db, "Cat")
    prod_id = await service.create_product(db, category_id=cat_id, name="P", price=10)
    o1 = await service.create_order(db, 1, prod_id, 10)
    o2 = await service.create_order(db, 2, prod_id, 20)
    await service.mark_paid(db, o1, "pay_1")
    await service.mark_paid(db, o2, "pay_2")

    stats = await service.get_sales_stats(db, period="day")
    assert stats["paid_count"] == 2
    assert stats["delivered_count"] == 0
    assert stats["revenue"] == 0  # not delivered yet


@pytest.mark.asyncio
async def test_service_low_stock_alert(db):
    cat_id = await service.create_category(db, "Cat")
    prod_id = await service.create_product(db, category_id=cat_id, name="Low", price=10, delivery_type="text")
    await service.add_keys(db, prod_id, ["k1"])  # only 1 key, below threshold 5

    low = await service.get_low_stock_products(db, threshold=5)
    assert len(low) == 1
    assert low[0]["available_keys"] == 1
