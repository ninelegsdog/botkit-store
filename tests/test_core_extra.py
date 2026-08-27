from __future__ import annotations

import asyncio
import time
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram import Bot
from aiogram.fsm.context import FSMContext, StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Chat, Message, User

from src.app import register_routers
from src.core.auth import AuthMiddleware
from src.core.bot_factory import AppState, create_app
from src.core.config import Config
from src.core.errors import RetryMiddleware, default_error_handler, register_error_handler
from src.core.fsm import AdminAuth, AdminCategory, AdminProduct, CartCheckout
from src.core.metrics import ORDERS_TOTAL, UPDATES_TOTAL, Metrics, UpdatesMiddleware
from src.core.nav import admin_menu, client_menu
from src.core.payments import MockPaymentProvider, PaymentProvider
from src.core.sentry import init_sentry
from src.core.storage import Storage
from src.core.throttling import ThrottlingMiddleware
from src.core.webhook import create_app as create_webhook_app


def _real_message(user_id: int = 1, text: str = "x") -> Message:
    return Message(
        message_id=1,
        chat=Chat(id=1, type="private"),
        date=datetime.now(),
        from_user=User(id=user_id, is_bot=False, first_name="U"),
        text=text,
    )


def _fsm(user_id: int = 1) -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=1, user_id=user_id, business_connection_id=None)
    return FSMContext(storage, key)


def _fake_db_with_session() -> MagicMock:
    db = MagicMock()
    cm = AsyncMock()
    sess = MagicMock()
    cm.__aenter__.return_value = sess
    cm.__aexit__.return_value = False
    db.session = MagicMock(return_value=cm)
    db.transaction = MagicMock(return_value=cm)
    return db, sess, cm


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
def test_config_from_env_reads_plain_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "tkn")
    monkeypatch.setenv("ADMIN_PASSWORD", "pw")
    monkeypatch.setenv("ADMIN_IDS", "1,2,3")
    monkeypatch.setenv("REDIS_URL", "redis://example/1")
    cfg = Config.from_env()
    assert cfg.bot_token == "tkn"
    assert cfg.admin_password == "pw"
    assert cfg.admin_ids == [1, 2, 3]
    assert cfg.redis_url == "redis://example/1"


@pytest.mark.parametrize("missing", ["BOT_TOKEN", "ADMIN_PASSWORD", "ADMIN_IDS"])
def test_config_validate_raises_when_required_missing(
    monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    monkeypatch.setenv("BOT_TOKEN", "tkn")
    monkeypatch.setenv("ADMIN_PASSWORD", "pw")
    monkeypatch.setenv("ADMIN_IDS", "1")
    monkeypatch.delenv(missing, raising=False)
    with pytest.raises(RuntimeError):
        Config.from_env().validate()


# --------------------------------------------------------------------------- #
# bot_factory
# --------------------------------------------------------------------------- #
def test_create_app_builds_state_with_memory_fsm() -> None:
    with patch(
        "src.core.bot_factory.RedisStorage.from_url", return_value=MemoryStorage()
    ):
        state = create_app(config=Config(bot_token="123456789:AAfake"))
    assert isinstance(state, AppState)
    assert isinstance(state.bot, Bot)
    assert state.fsm_storage is not None
    assert state.metrics is not None


# --------------------------------------------------------------------------- #
# ThrottlingMiddleware
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_throttling_passes_first_throttles_second() -> None:
    mw = ThrottlingMiddleware(min_interval=2.0)
    handler = AsyncMock(return_value="result")
    first = await mw(handler, _real_message(), {})
    assert first == "result"
    assert handler.await_count == 1

    mw._last_message[1] = time.time()
    second = await mw(handler, _real_message(), {})
    assert second is None
    assert handler.await_count == 1


@pytest.mark.asyncio
async def test_throttling_ignores_non_message_events() -> None:
    mw = ThrottlingMiddleware(min_interval=2.0)
    handler = AsyncMock(return_value="ok")
    result = await mw(handler, SimpleNamespace(), {})  # type: ignore[arg-type]
    assert result == "ok"
    assert handler.await_count == 1


# --------------------------------------------------------------------------- #
# Storage (SQL-backed get/set_setting)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_storage_get_setting_returns_value() -> None:
    db, sess, _ = _fake_db_with_session()
    result = MagicMock()
    result.fetchone = MagicMock(return_value=("v",))
    sess.execute = AsyncMock(return_value=result)
    storage = Storage(db)
    assert await storage.get_setting("k") == "v"


@pytest.mark.asyncio
async def test_storage_get_setting_none_when_empty() -> None:
    db, sess, _ = _fake_db_with_session()
    result = MagicMock()
    result.fetchone = MagicMock(return_value=None)
    sess.execute = AsyncMock(return_value=result)
    storage = Storage(db)
    assert await storage.get_setting("missing") is None


@pytest.mark.asyncio
async def test_storage_set_setting() -> None:
    db, sess, _ = _fake_db_with_session()
    sess.execute = AsyncMock()
    storage = Storage(db)
    await storage.set_setting("k", "v")
    assert sess.execute.await_count == 1


# --------------------------------------------------------------------------- #
# webhook
# --------------------------------------------------------------------------- #
def test_webhook_app_has_routes() -> None:
    state = SimpleNamespace(metrics=Metrics())
    app = create_webhook_app(state)  # type: ignore[arg-type]
    assert app.router.routes()
    assert len(app.router.routes()) >= 2


# --------------------------------------------------------------------------- #
# metrics
# --------------------------------------------------------------------------- #
def test_metrics_inc_messages_and_orders() -> None:
    m = Metrics()
    m.inc_messages()
    assert m.messages_processed == 1
    before = ORDERS_TOTAL._value.get()
    m.inc_orders()
    assert m.orders_created == 1
    assert ORDERS_TOTAL._value.get() == before + 1


def test_metrics_uptime_positive() -> None:
    m = Metrics()
    assert m.uptime_seconds() >= 0


@pytest.mark.asyncio
async def test_updates_middleware_increments_prometheus() -> None:
    mw = UpdatesMiddleware()
    handler = AsyncMock(return_value="ok")
    before = UPDATES_TOTAL.labels(type="message")._value.get()
    await mw(handler, _real_message(), {})
    after = UPDATES_TOTAL.labels(type="message")._value.get()
    assert after == before + 1


# --------------------------------------------------------------------------- #
# sentry
# --------------------------------------------------------------------------- #
def test_init_sentry_no_dsn_silent() -> None:
    init_sentry(None)


def test_init_sentry_missing_sdk() -> None:
    with patch.dict("sys.modules", {"sentry_sdk": None}):
        init_sentry("https://abc@sentry.io/1")


def test_init_sentry_valid_dsn() -> None:
    init_sentry("https://abc@sentry.io/1")


# --------------------------------------------------------------------------- #
# errors
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_default_error_handler_retry_after(monkeypatch: pytest.MonkeyPatch) -> None:
    slept: list[float] = []

    async def fake_sleep(s: float) -> None:
        slept.append(s)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    from aiogram.exceptions import TelegramRetryAfter

    exc = TelegramRetryAfter(None, "r", 0)
    await default_error_handler(None, exc)  # type: ignore[arg-type]
    assert 0.0 in slept


@pytest.mark.asyncio
async def test_default_error_handler_network() -> None:
    from aiogram.exceptions import TelegramNetworkError

    exc = TelegramNetworkError(None, "n")
    await default_error_handler(None, exc)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_default_error_handler_unhandled() -> None:
    await default_error_handler(None, ValueError("x"))  # type: ignore[arg-type]


def test_register_error_handler_on_fake_dispatcher() -> None:
    fake_dp = SimpleNamespace(error=MagicMock(return_value=MagicMock()))
    register_error_handler(fake_dp)
    assert fake_dp.error.called


@pytest.mark.asyncio
async def test_retry_middleware_retries_then_succeeds() -> None:
    from aiogram.exceptions import TelegramNetworkError

    calls = 0

    async def handler(event: object, data: dict) -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise TelegramNetworkError(None, "net")
        return "ok"

    mw = RetryMiddleware(max_retries=3, delay=0)
    assert await mw(handler, None, {}) == "ok"  # type: ignore[arg-type]
    assert calls == 2


@pytest.mark.asyncio
async def test_retry_middleware_raises_after_max() -> None:
    from aiogram.exceptions import TelegramNetworkError

    async def handler(event: object, data: dict) -> None:
        raise TelegramNetworkError(None, "net")

    mw = RetryMiddleware(max_retries=2, delay=0)
    with pytest.raises(TelegramNetworkError):
        await mw(handler, None, {})  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# fsm
# --------------------------------------------------------------------------- #
def test_fsm_states_groups_are_statesgroups() -> None:
    from aiogram.fsm.state import StatesGroup

    for cls in (CartCheckout, AdminAuth, AdminProduct, AdminCategory):
        assert issubclass(cls, StatesGroup)


# --------------------------------------------------------------------------- #
# nav
# --------------------------------------------------------------------------- #
def test_nav_menus_return_keyboards() -> None:
    assert client_menu().keyboard
    assert admin_menu().keyboard


# --------------------------------------------------------------------------- #
# auth middleware
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_auth_middleware_injects_db() -> None:
    db = MagicMock()
    mw = AuthMiddleware(db)
    captured: dict = {}

    async def handler(event: object, data: dict) -> None:
        captured.update(data)

    await mw(handler, SimpleNamespace(), {})  # type: ignore[arg-type]
    assert captured["db"] is db


# --------------------------------------------------------------------------- #
# payments
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_mock_payment_provider() -> None:
    provider: PaymentProvider = MockPaymentProvider()
    pid = await provider.create_payment(
        title="t", description="d", payload="p", amount=100
    )
    assert pid == "mock_payment_123"
    assert await provider.check_payment(pid) is True


# --------------------------------------------------------------------------- #
# app.register_routers
# --------------------------------------------------------------------------- #
def test_register_routers_includes_both() -> None:
    with patch(
        "src.core.bot_factory.RedisStorage.from_url", return_value=MemoryStorage()
    ):
        state = create_app(config=Config(bot_token="123456789:AAfake"))
    register_routers(state)
    assert state.dp.sub_routers



# --------------------------------------------------------------------------- #
# handlers (store + admin) — real handlers, Telegram send mocked at method level
# --------------------------------------------------------------------------- #
def _find_handler(router, kind: str, name: str):
    getters = {
        "message": router.message.handlers,
        "callback": router.callback_query.handlers,
    }
    for h in getters[kind]:
        if h.callback.__name__ == name:
            return h.callback
    raise AssertionError(f"handler {name} not found in {kind}")


def _patch_msg(monkeypatch: pytest.MonkeyPatch) -> list:
    calls: list = []

    async def fake_answer(self, text=None, **kwargs):
        calls.append(text)
        return None

    monkeypatch.setattr(Message, "answer", fake_answer)
    return calls


def _patch_cb(monkeypatch: pytest.MonkeyPatch) -> list:
    calls: list = []
    texts: list = []

    async def fake_cb_answer(self, text=None, **kwargs):
        calls.append(text)
        return None

    async def fake_edit_text(self, text=None, **kwargs):
        texts.append(text)
        return None

    async def fake_answer_cb(self, *a, **k):
        return None

    monkeypatch.setattr(CallbackQuery, "answer", fake_answer_cb)
    monkeypatch.setattr(Message, "edit_text", fake_edit_text)
    return texts


@pytest.mark.asyncio
async def test_store_cmd_start_sends_welcome(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.core.metrics import Metrics
    from src.store.handlers import create_store_router

    sent = _patch_msg(monkeypatch)
    state = SimpleNamespace(db=MagicMock(), metrics=Metrics())
    router = create_store_router(state)  # type: ignore[arg-type]
    await _find_handler(router, "message", "cmd_start")(_real_message(text="/start"))
    assert any("Добро пожаловать" in (s or "") for s in sent)


@pytest.mark.asyncio
async def test_store_buy_now_creates_order(db, monkeypatch: pytest.MonkeyPatch) -> None:
    from src.core.metrics import Metrics
    from src.store import service
    from src.store.handlers import create_store_router

    cat_id = await service.create_category(db, "Cat")
    prod_id = await service.create_product(db, category_id=cat_id, name="P", price=50)
    await service.add_to_cart(db, 1, prod_id)

    edited = _patch_cb(monkeypatch)
    state = SimpleNamespace(db=db, metrics=Metrics())
    router = create_store_router(state)  # type: ignore[arg-type]
    cb = CallbackQuery(
        id="1",
        from_user=User(id=1, is_bot=False, first_name="U"),
        chat_instance="x",
        message=_real_message(text="x"),
        data=f"store_buy:{prod_id}",
    )
    await _find_handler(router, "callback", "buy_now")(cb, state=_fsm())
    orders = await service.get_user_orders(db, 1)
    assert len(orders) == 1
    assert state.metrics.orders_created == 1
    assert edited


@pytest.mark.asyncio
async def test_store_show_catalog_lists_categories(db, monkeypatch: pytest.MonkeyPatch) -> None:
    from src.store import service
    from src.store.handlers import create_store_router

    await service.create_category(db, "CatA")
    sent = _patch_msg(monkeypatch)
    state = SimpleNamespace(db=db, metrics=MagicMock())
    router = create_store_router(state)  # type: ignore[arg-type]
    await _find_handler(router, "message", "show_catalog")(_real_message(text="🛍 Каталог"))
    assert sent


@pytest.mark.asyncio
async def test_admin_cmd_admin_sets_state(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.admin.handlers import create_admin_router
    from src.core.config import Config

    sent = _patch_msg(monkeypatch)
    app_state = SimpleNamespace(config=Config(admin_password="pw", admin_ids=[1]), db=MagicMock())
    router = create_admin_router(app_state)  # type: ignore[arg-type]
    fsm = _fsm()
    await _find_handler(router, "message", "cmd_admin")(_real_message(text="/admin"), state=fsm)
    assert await fsm.get_state() == AdminAuth.waiting_password
    assert any("Введите пароль" in (s or "") for s in sent)


@pytest.mark.asyncio
async def test_admin_check_password_correct_welcome(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.admin.handlers import create_admin_router
    from src.core.config import Config

    sent = _patch_msg(monkeypatch)
    app_state = SimpleNamespace(config=Config(admin_password="pw", admin_ids=[1]), db=MagicMock())
    router = create_admin_router(app_state)  # type: ignore[arg-type]
    msg = _real_message(text="pw")
    fsm = _fsm()
    await fsm.set_state(AdminAuth.waiting_password)
    await _find_handler(router, "message", "check_password")(msg, state=fsm)
    assert any("Добро пожаловатесь" in (s or "") for s in sent)
    assert await fsm.get_state() is None


@pytest.mark.asyncio
async def test_admin_check_password_wrong(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.admin.handlers import create_admin_router
    from src.core.config import Config

    sent = _patch_msg(monkeypatch)
    app_state = SimpleNamespace(config=Config(admin_password="pw", admin_ids=[1]), db=MagicMock())
    router = create_admin_router(app_state)  # type: ignore[arg-type]
    msg = _real_message(text="nope")
    fsm = _fsm()
    await fsm.set_state(AdminAuth.waiting_password)
    await _find_handler(router, "message", "check_password")(msg, state=fsm)
    assert any("Неверный пароль" in (s or "") for s in sent)


@pytest.mark.asyncio
async def test_admin_list_products_early_return_when_not_admin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.admin.handlers import create_admin_router
    from src.core.config import Config

    sent = _patch_msg(monkeypatch)
    app_state = SimpleNamespace(config=Config(admin_password="pw", admin_ids=[99]), db=MagicMock())
    router = create_admin_router(app_state)  # type: ignore[arg-type]
    await _find_handler(router, "message", "list_products")(_real_message(text="🛍 Товары"))
    assert sent == []


@pytest.mark.asyncio
async def test_admin_list_products_as_admin(db, monkeypatch: pytest.MonkeyPatch) -> None:
    from src.admin.handlers import create_admin_router
    from src.core.config import Config
    from src.store import service as store_svc

    await store_svc.create_category(db, "Cat")
    sent = _patch_msg(monkeypatch)
    app_state = SimpleNamespace(config=Config(admin_password="pw", admin_ids=[1]), db=db)
    router = create_admin_router(app_state)  # type: ignore[arg-type]
    await _find_handler(router, "message", "list_products")(_real_message(text="🛍 Товары"))
    assert sent
