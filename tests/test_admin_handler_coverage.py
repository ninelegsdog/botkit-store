from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.admin.handlers import create_admin_router
from src.core.auth import AdminGate
from src.core.config import Config


def _msg(user_id: int = 1, text: str = "x") -> MagicMock:
    m = MagicMock()
    m.from_user = MagicMock()
    m.from_user.id = user_id
    m.text = text
    m.answer = AsyncMock()
    m.edit_text = AsyncMock()
    return m


def _cb(user_id: int = 1, data: str = "t") -> MagicMock:
    c = MagicMock()
    c.from_user = MagicMock()
    c.from_user.id = user_id
    c.data = data
    c.message = _msg(user_id, text="orig")
    c.answer = AsyncMock()
    c.message.edit_text = AsyncMock()
    return c


def _state():
    s = MagicMock()
    s.set_state = AsyncMock()
    s.clear = AsyncMock()
    s.update_data = AsyncMock()
    s.get_data = AsyncMock(return_value={})
    return s


def _app(admin_ids=None):
    cfg = Config(bot_token="t", admin_password="pw", admin_ids=admin_ids or [1])
    a = MagicMock()
    a.config = cfg
    a.db = MagicMock()
    return a


def _router(app=None):
    return create_admin_router(app or _app())


def _find(router, kind, name):
    hs = router.message.handlers if kind == "message" else router.callback_query.handlers
    for h in hs:
        if h.callback.__name__ == name:
            return h.callback
    return None


# ── admin password flow ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cmd_admin():
    cb = _find(_router(), "message", "cmd_admin")
    assert cb is not None
    m = _msg(1, "/admin")
    st = _state()
    await cb(m, st)
    m.answer.assert_called_once()


# ── categories: list (admin path) ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_categories_admin_nonempty():
    app = _app()
    r = _router(app)
    cb = _find(r, "message", "list_categories")
    assert cb is not None
    m = _msg(1, "🗂 Категории")
    with patch(
        "src.admin.handlers.service.get_categories_admin",
        AsyncMock(return_value=[{"id": 1, "name": "C", "is_active": 1, "product_count": 0}]),
    ):
        await cb(m)
    m.answer.assert_called_once()


# ── categories: callback list ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cb_cat_list_nonempty():
    r = _router()
    cb = _find(r, "callback_query", "cb_cat_list")
    assert cb is not None
    q = _cb(1, "admin_cat_list")
    with patch(
        "src.admin.handlers.service.get_categories_admin",
        AsyncMock(return_value=[{"id": 1, "name": "C", "is_active": 1, "product_count": 0}]),
    ):
        await cb(q)
    q.answer.assert_called()


# ── categories: open category ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cb_cat_open_found():
    r = _router()
    cb = _find(r, "callback_query", "cb_cat_open")
    assert cb is not None
    q = _cb(1, "admin_cat:1")
    with patch(
        "src.admin.handlers.service.get_categories_admin",
        AsyncMock(return_value=[{"id": 1, "name": "C", "is_active": 1, "product_count": 0}]),
    ):
        await cb(q)
    q.answer.assert_called()


@pytest.mark.asyncio
async def test_cb_cat_open_not_found():
    r = _router()
    cb = _find(r, "callback_query", "cb_cat_open")
    assert cb is not None
    q = _cb(1, "admin_cat:999")
    with patch(
        "src.admin.handlers.service.get_categories_admin",
        AsyncMock(return_value=[]),
    ):
        await cb(q)
    q.answer.assert_called_once()


# ── categories: add flow ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cb_cat_add():
    r = _router()
    cb = _find(r, "callback_query", "cb_cat_add")
    assert cb is not None
    q = _cb(1, "admin_cat_add")
    st = _state()
    await cb(q, st)
    q.answer.assert_called()


@pytest.mark.asyncio
async def test_cat_enter_name():
    r = _router()
    cb = _find(r, "message", "cat_enter_name")
    assert cb is not None
    m = _msg(1, "NewCat")
    st = _state()
    await cb(m, st)
    m.answer.assert_called()


@pytest.mark.asyncio
async def test_cat_enter_position():
    r = _router()
    cb = _find(r, "message", "cat_enter_position")
    assert cb is not None
    m = _msg(1, "3")
    st = _state()
    st.get_data = AsyncMock(return_value={"cat_name": "NewCat", "cat_action": "create"})
    with patch(
        "src.admin.handlers.service.create_category",
        AsyncMock(return_value=1),
    ), patch(
        "src.admin.handlers.service.get_categories_admin",
        AsyncMock(return_value=[{"id": 1, "name": "NewCat", "product_count": 0}]),
    ):
        await cb(m, st)
    m.answer.assert_called()


# ── categories: edit ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cb_cat_edit():
    r = _router()
    cb = _find(r, "callback_query", "cb_cat_edit")
    assert cb is not None
    q = _cb(1, "admin_cat_edit:1")
    st = _state()
    await cb(q, st)
    q.answer.assert_called()


# ── categories: toggle ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cb_cat_toggle():
    r = _router()
    cb = _find(r, "callback_query", "cb_cat_toggle")
    assert cb is not None
    q = _cb(1, "admin_cat_toggle:1")
    with patch(
        "src.admin.handlers.service.toggle_category",
        AsyncMock(return_value=True),
    ), patch(
        "src.admin.handlers.service.get_categories_admin",
        AsyncMock(return_value=[]),
    ):
        await cb(q)
    q.answer.assert_called()


# ── categories: delete flow ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cb_cat_del():
    r = _router()
    cb = _find(r, "callback_query", "cb_cat_del")
    assert cb is not None
    q = _cb(1, "admin_cat_del:1")
    await cb(q)
    q.answer.assert_called()


@pytest.mark.asyncio
async def test_cb_confirm_cat_del_ok():
    r = _router()
    cb = _find(r, "callback_query", "cb_confirm_cat_del")
    assert cb is not None
    q = _cb(1, "admin_confirm:cat_del:1")
    with patch(
        "src.admin.handlers.service.delete_category",
        AsyncMock(return_value=True),
    ):
        await cb(q)
    q.answer.assert_called()


# ── products: open product ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cb_prod_open_found():
    r = _router()
    cb = _find(r, "callback_query", "cb_prod_open")
    assert cb is not None
    q = _cb(1, "admin_prod:1")
    with patch(
        "src.admin.handlers.service.get_product_admin",
        AsyncMock(return_value={"id": 1, "name": "P", "price": 10, "is_active": 1}),
    ), patch(
        "src.admin.handlers.service.get_stock",
        AsyncMock(return_value={"total": 0, "used": 0, "available": 0}),
    ):
        await cb(q)
    q.answer.assert_called()


@pytest.mark.asyncio
async def test_cb_prod_open_not_found():
    r = _router()
    cb = _find(r, "callback_query", "cb_prod_open")
    assert cb is not None
    q = _cb(1, "admin_prod:999")
    with patch(
        "src.admin.handlers.service.get_product_admin",
        AsyncMock(return_value=None),
    ):
        await cb(q)
    q.answer.assert_called_once()


# ── products: add flow start ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cb_prod_add_start():
    r = _router()
    cb = _find(r, "callback_query", "cb_prod_add_start")
    assert cb is not None
    q = _cb(1, "admin_cat_add_prod:1")
    st = _state()
    await cb(q, st)
    q.answer.assert_called()


# ── products: FSM name ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_prod_enter_name():
    r = _router()
    cb = _find(r, "message", "prod_enter_name")
    assert cb is not None
    m = _msg(1, "NewProd")
    st = _state()
    await cb(m, st)
    m.answer.assert_called()


# ── products: toggle ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cb_prod_toggle():
    r = _router()
    cb = _find(r, "callback_query", "cb_prod_toggle")
    assert cb is not None
    q = _cb(1, "admin_prod_toggle:1")
    with patch(
        "src.admin.handlers.service.toggle_product",
        AsyncMock(return_value=True),
    ), patch(
        "src.admin.handlers.service.get_products",
        AsyncMock(return_value=[]),
    ), patch(
        "src.admin.handlers.service.get_categories_admin",
        AsyncMock(return_value=[]),
    ):
        await cb(q)
    q.answer.assert_called()


# ── products: keys ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cb_prod_keys():
    r = _router()
    cb = _find(r, "callback_query", "cb_prod_keys")
    assert cb is not None
    q = _cb(1, "admin_prod_keys:1")
    st = _state()
    await cb(q, st)
    q.answer.assert_called()


# ── products: delete ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cb_prod_del():
    r = _router()
    cb = _find(r, "callback_query", "cb_prod_del")
    assert cb is not None
    q = _cb(1, "admin_prod_del:1")
    await cb(q)
    q.answer.assert_called()


# ── orders: list ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_orders_nonempty():
    r = _router()
    cb = _find(r, "message", "list_orders")
    assert cb is not None
    m = _msg(1, "📦 Заказы")
    with patch(
        "src.admin.handlers.service.get_orders_by_status",
        AsyncMock(return_value=[{"id": 1, "status": "paid", "amount": 10, "product_name": "P", "user_id": 1}]),
    ):
        await cb(m)
    m.answer.assert_called()


# ── orders: open ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cb_order_open():
    r = _router()
    cb = _find(r, "callback_query", "cb_order_open")
    assert cb is not None
    q = _cb(1, "admin_order:1")
    with patch(
        "src.admin.handlers.service.get_orders_by_status",
        AsyncMock(return_value=[{"id": 1, "status": "paid", "amount": 10, "product_name": "P", "user_id": 1}]),
    ):
        await cb(q)
    q.answer.assert_called()


# ── orders: fulfill ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cb_order_fulfill():
    r = _router()
    cb = _find(r, "callback_query", "cb_order_fulfill")
    assert cb is not None
    q = _cb(1, "admin_order_fulfill:1")
    st = _state()
    with patch(
        "src.admin.handlers.service.manual_fulfill_order",
        AsyncMock(return_value=True),
    ):
        await cb(q, st)
    q.answer.assert_called()


# ── orders: cancel ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cb_order_cancel():
    r = _router()
    cb = _find(r, "callback_query", "cb_order_cancel")
    assert cb is not None
    q = _cb(1, "admin_order_cancel:1")
    await cb(q)
    q.answer.assert_called()


# ── orders: refund ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cb_order_refund():
    r = _router()
    cb = _find(r, "callback_query", "cb_order_refund")
    assert cb is not None
    q = _cb(1, "admin_order_refund:1")
    await cb(q)
    q.answer.assert_called()


# ── confirmations ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cb_confirm_prod_del():
    r = _router()
    cb = _find(r, "callback_query", "cb_confirm_prod_del")
    assert cb is not None
    q = _cb(1, "admin_confirm:prod_del:1")
    with patch(
        "src.admin.handlers.service.delete_product",
        AsyncMock(return_value=True),
    ):
        await cb(q)
    q.answer.assert_called()


@pytest.mark.asyncio
async def test_cb_confirm_order_cancel():
    r = _router()
    cb = _find(r, "callback_query", "cb_confirm_order_cancel")
    assert cb is not None
    q = _cb(1, "admin_confirm:order_cancel:1")
    with patch(
        "src.admin.handlers.service.cancel_order",
        AsyncMock(return_value=True),
    ):
        await cb(q)
    q.answer.assert_called()


@pytest.mark.asyncio
async def test_cb_confirm_order_refund():
    r = _router()
    cb = _find(r, "callback_query", "cb_confirm_order_refund")
    assert cb is not None
    q = _cb(1, "admin_confirm:order_refund:1")
    with patch(
        "src.admin.handlers.service.refund_order",
        AsyncMock(return_value=True),
    ):
        await cb(q)
    q.answer.assert_called()


# ── navigation ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cb_admin_back():
    r = _router()
    cb = _find(r, "callback_query", "cb_admin_back")
    assert cb is not None
    q = _cb(1, "admin_back")
    await cb(q)
    q.answer.assert_called()


# ── AdminGate ───────────────────────────────────────────────────────────────

def test_gate_is_admin_false():
    g = AdminGate("pw", [999])
    assert g.is_admin(1) is False


def test_gate_is_admin_true():
    g = AdminGate("pw", [1])
    assert g.is_admin(1) is True


# ── products: FSM description, price, delivery ──────────────────────────────

@pytest.mark.asyncio
async def test_prod_enter_description():
    r = _router()
    cb = _find(r, "message", "prod_enter_description")
    assert cb is not None
    m = _msg(1, "Desc")
    st = _state()
    await cb(m, st)
    m.answer.assert_called()


@pytest.mark.asyncio
async def test_prod_enter_price():
    r = _router()
    cb = _find(r, "message", "prod_enter_price")
    assert cb is not None
    m = _msg(1, "100")
    st = _state()
    await cb(m, st)
    m.answer.assert_called()


@pytest.mark.asyncio
async def test_prod_enter_price_invalid():
    r = _router()
    cb = _find(r, "message", "prod_enter_price")
    assert cb is not None
    m = _msg(1, "not_a_number")
    st = _state()
    await cb(m, st)
    m.answer.assert_called()


@pytest.mark.asyncio
async def test_prod_enter_delivery_type():
    r = _router()
    cb = _find(r, "message", "prod_enter_delivery_type")
    assert cb is not None
    m = _msg(1, "1")
    st = _state()
    await cb(m, st)
    m.answer.assert_called()


# ── products: FSM keys batch ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_prod_enter_keys():
    r = _router()
    cb = _find(r, "message", "prod_enter_keys")
    assert cb is not None
    m = _msg(1, "key1\nkey2")
    st = _state()
    await cb(m, st)
    m.answer.assert_called()


# ── products: FSM photo ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_prod_enter_photo():
    r = _router()
    cb = _find(r, "message", "prod_enter_photo")
    assert cb is not None
    m = _msg(1, "file_id_123")
    st = _state()
    st.get_data = AsyncMock(return_value={
        "cat_id": 1, "prod_name": "P", "prod_price": 100, "prod_description": "",
        "prod_delivery_type": "text", "prod_keys": []
    })
    with patch(
        "src.admin.handlers.service.create_product",
        AsyncMock(return_value=1),
    ):
        await cb(m, st)
    m.answer.assert_called()


# ── products: edit ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cb_prod_edit():
    r = _router()
    cb = _find(r, "callback_query", "cb_prod_edit")
    assert cb is not None
    q = _cb(1, "admin_prod_edit:1")
    st = _state()
    await cb(q, st)
    q.answer.assert_called()


# ── orders: cancel confirm ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cb_confirm_order_cancel_ok():
    r = _router()
    cb = _find(r, "callback_query", "cb_confirm_order_cancel")
    assert cb is not None
    q = _cb(1, "admin_confirm:order_cancel:1")
    with patch(
        "src.admin.handlers.service.cancel_order",
        AsyncMock(return_value=True),
    ):
        await cb(q)
    q.answer.assert_called()


# ── products: confirm delete refused ────────────────────────────────────────

@pytest.mark.asyncio
async def test_cb_confirm_prod_del_refused():
    r = _router()
    cb = _find(r, "callback_query", "cb_confirm_prod_del")
    assert cb is not None
    q = _cb(1, "admin_confirm:prod_del:1")
    with patch(
        "src.admin.handlers.service.delete_product",
        AsyncMock(return_value=False),
    ):
        await cb(q)
    q.answer.assert_called()


# ── categories: confirm delete refused ──────────────────────────────────────

@pytest.mark.asyncio
async def test_cb_confirm_cat_del_refused():
    r = _router()
    cb = _find(r, "callback_query", "cb_confirm_cat_del")
    assert cb is not None
    q = _cb(1, "admin_confirm:cat_del:1")
    with patch(
        "src.admin.handlers.service.delete_category",
        AsyncMock(return_value=False),
    ):
        await cb(q)
    q.answer.assert_called()


# ── FSM: cancel confirm ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cb_cancel_confirm():
    r = _router()
    cb = _find(r, "callback_query", "cb_cancel_confirm")
    assert cb is not None
    q = _cb(1, "admin_cancel_confirm")
    await cb(q)
    q.answer.assert_called()
