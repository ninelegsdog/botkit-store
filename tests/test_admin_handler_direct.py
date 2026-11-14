from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.admin.handlers import create_admin_router
from src.core.auth import AdminGate
from src.core.config import Config
from src.core.fsm import AdminCategory, AdminOrder, AdminProduct


def _fake_message(user_id: int = 1, text: str = "x") -> MagicMock:
    msg = MagicMock()
    msg.from_user = MagicMock()
    msg.from_user.id = user_id
    msg.text = text
    msg.answer = AsyncMock()
    msg.edit_text = AsyncMock()
    return msg


def _fake_callback(user_id: int = 1, data: str = "test") -> MagicMock:
    cb = MagicMock()
    cb.from_user = MagicMock()
    cb.from_user.id = user_id
    cb.data = data
    cb.message = _fake_message(user_id, text="orig")
    cb.answer = AsyncMock()
    cb.message.edit_text = AsyncMock()
    return cb


def _fake_app_state():
    config = Config(
        bot_token="test",
        admin_password="secret",
        admin_ids=[1],
    )
    app_state = MagicMock()
    app_state.config = config
    app_state.db = MagicMock()
    return app_state


def _find_handler(router, kind, name):
    handlers = router.message.handlers if kind == "message" else router.callback_query.handlers
    for h in handlers:
        if h.callback.__name__ == name:
            return h.callback
    return None


# ── AdminGate ───────────────────────────────────────────────────────────────

def test_admin_gate_authorize():
    gate = AdminGate("pw", [1])
    assert gate.authorize(1, "pw") is True
    assert gate.authorize(1, "wrong") is False
    # is_admin checks admin_ids list (config), so user in admin_ids is admin
    assert gate.is_admin(1) is True


def test_admin_gate_throttling():
    gate = AdminGate("pw", [999])
    assert gate.is_throttled(1) is False
    for _ in range(5):
        gate.authorize(1, "wrong")
    assert gate.is_throttled(1) is True


# ── Admin auth handlers ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_wrong_password_flow():
    app_state = _fake_app_state()
    router = create_admin_router(app_state)
    cb = _find_handler(router, "message", "check_password")
    assert cb is not None
    message = _fake_message(1, "wrong")
    state = MagicMock()
    state.set_state = AsyncMock()
    state.clear = AsyncMock()
    await cb(message, state)
    message.answer.assert_called_once()


@pytest.mark.asyncio
async def test_admin_correct_password_flow():
    app_state = _fake_app_state()
    router = create_admin_router(app_state)
    cb = _find_handler(router, "message", "check_password")
    assert cb is not None
    message = _fake_message(1, "secret")
    state = MagicMock()
    state.set_state = AsyncMock()
    state.clear = AsyncMock()
    await cb(message, state)
    assert message.answer.call_count >= 1


# ── Non-admin access ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_categories_non_admin():
    config = Config(bot_token="test", admin_password="secret", admin_ids=[999])
    app_state = MagicMock()
    app_state.config = config
    app_state.db = MagicMock()
    router = create_admin_router(app_state)
    cb = _find_handler(router, "message", "list_categories")
    assert cb is not None
    message = _fake_message(1, "🗂 Категории")
    await cb(message)
    message.answer.assert_not_called()


@pytest.mark.asyncio
async def test_all_handlers_reject_non_admin():
    config = Config(bot_token="test", admin_password="secret", admin_ids=[999])
    app_state = MagicMock()
    app_state.config = config
    app_state.db = MagicMock()
    router = create_admin_router(app_state)
    for name in ("list_categories", "list_products", "list_orders", "sales_stats", "stock_low"):
        cb = _find_handler(router, "message", name)
        assert cb is not None, f"handler {name} not found"
        message = _fake_message(1, "x")
        await cb(message)
        message.answer.assert_not_called()


# ── Sales stats ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sales_stats_admin():
    app_state = _fake_app_state()
    router = create_admin_router(app_state)
    cb = _find_handler(router, "message", "sales_stats")
    assert cb is not None
    message = _fake_message(1, "📊 Продажи")
    with patch("src.admin.handlers.service.get_sales_stats", AsyncMock(return_value={
        "paid_count": 1, "delivered_count": 0, "revenue": 0, "refunded_count": 0
    })):
        await cb(message)
    message.answer.assert_called_once()


# ── Stock low ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stock_low_admin():
    app_state = _fake_app_state()
    router = create_admin_router(app_state)
    cb = _find_handler(router, "message", "stock_low")
    assert cb is not None
    message = _fake_message(1, "⚠️ Остатки ключей")
    with patch("src.admin.handlers.service.get_low_stock_products", AsyncMock(return_value=[])):
        await cb(message)
    message.answer.assert_called_once()


# ── Callback: category toggle ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cb_cat_toggle():
    app_state = _fake_app_state()
    router = create_admin_router(app_state)
    cb = _find_handler(router, "callback_query", "cb_cat_toggle")
    assert cb is not None
    query = _fake_callback(1, "admin_cat_toggle:5")
    with patch("src.admin.handlers.service.toggle_category", AsyncMock(return_value=True)), \
         patch("src.admin.handlers.service.get_categories_admin", AsyncMock(return_value=[])):
        await cb(query)
    query.answer.assert_called()


# ── Callback: order fulfill ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cb_order_fulfill():
    app_state = _fake_app_state()
    router = create_admin_router(app_state)
    cb = _find_handler(router, "callback_query", "cb_order_fulfill")
    assert cb is not None
    query = _fake_callback(1, "admin_order_fulfill:42")
    state = MagicMock()
    state.set_state = AsyncMock()
    state.update_data = AsyncMock()
    with patch("src.admin.handlers.service.manual_fulfill_order", AsyncMock(return_value=True)):
        await cb(query, state)
    query.answer.assert_called()


# ── FSM handlers ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fsm_cat_enter_name():
    app_state = _fake_app_state()
    router = create_admin_router(app_state)
    cb = _find_handler(router, "message", "cat_enter_name")
    assert cb is not None
    message = _fake_message(1, "New Category")
    state = MagicMock()
    state.set_state = AsyncMock()
    state.clear = AsyncMock()
    state.update_data = AsyncMock()
    await state.set_state(AdminCategory.entering_name)
    await cb(message, state)
    message.answer.assert_called_once()


@pytest.mark.asyncio
async def test_fsm_prod_enter_name():
    app_state = _fake_app_state()
    router = create_admin_router(app_state)
    cb = _find_handler(router, "message", "prod_enter_name")
    assert cb is not None
    message = _fake_message(1, "New Product")
    state = MagicMock()
    state.set_state = AsyncMock()
    state.clear = AsyncMock()
    state.update_data = AsyncMock()
    await state.set_state(AdminProduct.entering_name)
    await cb(message, state)
    message.answer.assert_called_once()


@pytest.mark.asyncio
async def test_fsm_order_fulfill_enter():
    app_state = _fake_app_state()
    router = create_admin_router(app_state)
    cb = _find_handler(router, "message", "order_fulfill_enter")
    assert cb is not None
    message = _fake_message(1, "manual-key")
    state = MagicMock()
    state.set_state = AsyncMock()
    state.clear = AsyncMock()
    state.update_data = AsyncMock()
    state.get_data = AsyncMock(return_value={"order_id": 42})
    await state.set_state(AdminOrder.confirming_fulfill)
    with patch("src.admin.handlers.service.manual_fulfill_order", AsyncMock(return_value=True)):
        await cb(message, state)
    message.answer.assert_called_once()
