from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Chat, Message, User

from src.core.bot_factory import AppState
from src.core.config import Config
from src.store import service
from src.store.handlers import create_store_router

BUYER = 123


def _fsm(user_id: int = BUYER) -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=1, user_id=user_id, business_connection_id=None)
    return FSMContext(storage, key)


def _make_callback(data: str | None, user_id: int = BUYER) -> MagicMock:
    cb = MagicMock(spec=CallbackQuery)
    cb.data = data
    cb.from_user = User(id=user_id, is_bot=False, first_name="U")
    msg = MagicMock()
    msg.edit_text = AsyncMock()
    msg.answer = AsyncMock()
    cb.message = msg
    cb.answer = AsyncMock()
    return cb


def _make_message(text: str, user_id: int = BUYER) -> MagicMock:
    msg = MagicMock(spec=Message)
    msg.message_id = 1
    msg.chat = Chat(id=1, type="private")
    msg.date = None
    msg.from_user = User(id=user_id, is_bot=False, first_name="U")
    msg.text = text
    msg.answer = AsyncMock()
    return msg


def _app_state(db) -> AppState:
    config = Config(db_path=":memory:")
    with patch.object(Bot, "__init__", return_value=None):
        state = AppState(config)
    state.db = db
    return state


async def _seed_product(db, name: str = "Продукт", price: int = 100) -> int:
    cat_id = await service.create_category(db, "Тест")
    return await service.create_product(db, category_id=cat_id, name=name, price=price)


async def _seed_order(db, user_id: int = BUYER, amount: int = 100) -> int:
    cat_id = await service.create_category(db, "Заказ")
    prod_id = await service.create_product(
        db, category_id=cat_id, name="Товар", price=amount
    )
    return await service.create_order(db, user_id, prod_id, amount)


# --------------------------------------------------------------------------- #
# start / catalog
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_start_clears_state(db):
    app_state = _app_state(db)
    router = create_store_router(app_state)
    handler = _find(router, "message", "cmd_start")
    msg = _make_message("/start")
    await handler(msg, _fsm())
    msg.answer.assert_awaited()


@pytest.mark.asyncio
async def test_show_catalog_empty(db):
    state = _app_state(db)
    router = create_store_router(state)
    handler = _find(router, "message", "show_catalog")
    msg = _make_message("🛍 Каталог")
    await handler(msg)
    msg.answer.assert_awaited()


# --------------------------------------------------------------------------- #
# category / product
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_show_category_no_products(db):
    state = _app_state(db)
    router = create_store_router(state)
    handler = _find(router, "callback_query", "show_category")
    cb = _make_callback("store_cat:1")
    await handler(cb)
    cb.message.edit_text.assert_awaited()
    cb.answer.assert_awaited()


@pytest.mark.asyncio
async def test_show_category_with_products(db):
    app_state = _app_state(db)
    cat_id = await service.create_category(db, "Кат")
    await service.create_product(db, category_id=cat_id, name="Товар", price=100)
    router = create_store_router(app_state)
    handler = _find(router, "callback_query", "show_category")
    cb = _make_callback(f"store_cat:{cat_id}")
    await handler(cb)
    cb.message.answer.assert_awaited()
    cb.answer.assert_awaited()


@pytest.mark.asyncio
async def test_show_category_bad_data(db):
    state = _app_state(db)
    router = create_store_router(state)
    handler = _find(router, "callback_query", "show_category")
    cb = _make_callback(None)
    await handler(cb)
    cb.answer.assert_not_awaited()


# --------------------------------------------------------------------------- #
# cart
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_add_to_cart(db):
    state = _app_state(db)
    prod_id = await _seed_product(db)
    router = create_store_router(state)
    handler = _find(router, "callback_query", "add_to_cart")
    cb = _make_callback(f"store_cart:{prod_id}")
    await handler(cb)
    cb.answer.assert_awaited()


@pytest.mark.asyncio
async def test_add_to_cart_bad_data(db):
    state = _app_state(db)
    router = create_store_router(state)
    handler = _find(router, "callback_query", "add_to_cart")
    cb = _make_callback(None)
    await handler(cb)
    cb.answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_show_cart_empty(db):
    state = _app_state(db)
    router = create_store_router(state)
    handler = _find(router, "message", "show_cart")
    msg = _make_message("🛒 Корзина")
    await handler(msg)
    msg.answer.assert_awaited()


# --------------------------------------------------------------------------- #
# buy / checkout
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_buy_now(db):
    app_state = _app_state(db)
    prod_id = await _seed_product(db)
    router = create_store_router(app_state)
    handler = _find(router, "callback_query", "buy_now")
    cb = _make_callback(f"store_buy:{prod_id}")
    await handler(cb, _fsm())
    cb.message.edit_text.assert_awaited()
    cb.answer.assert_awaited()


@pytest.mark.asyncio
async def test_buy_now_product_not_found(db):
    app_state = _app_state(db)
    router = create_store_router(app_state)
    handler = _find(router, "callback_query", "buy_now")
    cb = _make_callback("store_buy:999999")
    await handler(cb, _fsm())
    cb.answer.assert_awaited()


@pytest.mark.asyncio
async def test_buy_now_bad_data(db):
    app_state = _app_state(db)
    router = create_store_router(app_state)
    handler = _find(router, "callback_query", "buy_now")
    cb = _make_callback(None)
    await handler(cb, _fsm())
    cb.answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_checkout_empty_cart(db):
    state = _app_state(db)
    router = create_store_router(state)
    handler = _find(router, "callback_query", "checkout")
    cb = _make_callback("store_checkout")
    await handler(cb)
    cb.answer.assert_awaited()


@pytest.mark.asyncio
async def test_checkout_with_cart(db):
    state = _app_state(db)
    prod_id = await _seed_product(db)
    await service.add_to_cart(db, BUYER, prod_id)
    router = create_store_router(state)
    handler = _find(router, "callback_query", "checkout")
    cb = _make_callback("store_checkout")
    await handler(cb)
    cb.message.edit_text.assert_awaited()
    cb.answer.assert_awaited()


# --------------------------------------------------------------------------- #
# paid / orders / redeliver
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_on_paid(db):
    state = _app_state(db)
    router = create_store_router(state)
    handler = _find(router, "message", "on_paid")
    msg = _make_message("")
    sp = MagicMock()
    sp.invoice_payload = "orders:1"
    sp.telegram_payment_charge_id = "chg-1"
    msg.successful_payment = sp
    await handler(msg)
    msg.answer.assert_awaited()


@pytest.mark.asyncio
async def test_on_paid_no_payment(db):
    state = _app_state(db)
    router = create_store_router(state)
    handler = _find(router, "message", "on_paid")
    msg = _make_message("")
    msg.successful_payment = None
    await handler(msg)
    msg.answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_my_orders_empty(db):
    state = _app_state(db)
    router = create_store_router(state)
    handler = _find(router, "message", "my_orders")
    msg = _make_message("📦 Мои покупки")
    await handler(msg)
    msg.answer.assert_awaited()


@pytest.mark.asyncio
async def test_redeliver_not_found(db):
    state = _app_state(db)
    router = create_store_router(state)
    handler = _find(router, "callback_query", "redeliver")
    cb = _make_callback("store_redeliver:999999")
    await handler(cb)
    cb.answer.assert_awaited()


@pytest.mark.asyncio
async def test_redeliver_bad_data(db):
    state = _app_state(db)
    router = create_store_router(state)
    handler = _find(router, "callback_query", "redeliver")
    cb = _make_callback(None)
    await handler(cb)
    cb.answer.assert_not_awaited()


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def _find(router, attr: str, name: str):
    handlers = getattr(router, attr).handlers
    for h in handlers:
        cb = h.callback
        if hasattr(cb, "__name__") and cb.__name__ == name:
            return cb
    raise AssertionError(f"handler {name!r} not found")
