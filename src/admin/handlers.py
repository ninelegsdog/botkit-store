from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from src.core.auth import AdminGate
from src.core.bot_factory import AppState
from src.core.fsm import AdminAuth
from src.core.navigation import admin_menu, client_menu
from src.store import service


def create_admin_router(app_state: AppState) -> Router:
    router = Router()
    db = app_state.db
    # The gate exists and is unit-tested, but the password check below ran raw: no attempt
    # limit, and a plain == that is timing-observable. Authorising through the gate gives
    # hmac.compare_digest and records failed attempts.
    gate = AdminGate(
        app_state.config.admin_password, app_state.config.admin_ids or []
    )

    def is_admin(user_id: int) -> bool:
        # Unchanged semantics: config admins, plus anyone the gate has authorised.
        return gate.is_admin(user_id)

    @router.message(Command("admin"))
    async def cmd_admin(message: Message, state: FSMContext) -> None:
        await state.set_state(AdminAuth.waiting_password)
        await message.answer("🔑 Введите пароль:")

    @router.message(AdminAuth.waiting_password)
    async def check_password(message: Message, state: FSMContext) -> None:
        user_id = message.from_user.id  # type: ignore[union-attr]
        if gate.is_throttled(user_id):
            await state.clear()
            await message.answer(
                "⏳ Слишком много попыток. Попробуйте через 5 минут.",
                reply_markup=client_menu(),
            )
            return
        if gate.authorize(user_id, message.text or ""):
            await state.clear()
            await message.answer("✅ Добро пожаловать!", reply_markup=admin_menu())
        else:
            await state.clear()
            await message.answer("❌ Неверный пароль.", reply_markup=client_menu())

    @router.message(F.text == "🛍 Товары")
    async def list_products(message: Message) -> None:
        if not is_admin(message.from_user.id):  # type: ignore[union-attr]
            return
        categories = await service.get_categories(db)
        if not categories:
            await message.answer("Нет категорий.")
            return
        text = "🛍 Категории:\n" + "\n".join(
            f"• {c['name']} (ID: {c['id']})" for c in categories
        )
        await message.answer(text)

    @router.message(F.text == "📦 Заказы")
    async def list_orders(message: Message) -> None:
        if not is_admin(message.from_user.id):  # type: ignore[union-attr]
            return
        day = await service.get_order_stats(db, "day")
        week = await service.get_order_stats(db, "week")
        await message.answer(
            f"📦 Статистика заказов:\n\nСегодня:\n"
            f"  Оплачено: {day.get('paid', 0) + day.get('delivered', 0)}\n"
            f"  Ожидает: {day.get('pending_payment', 0)}\n\n"
            f"За неделю:\n"
            f"  Оплачено: {week.get('paid', 0) + week.get('delivered', 0)}\n"
            f"  Ожидает: {week.get('pending_payment', 0)}"
        )

    @router.message(F.text == "📊 Продажи")
    async def sales_stats(message: Message) -> None:
        if not is_admin(message.from_user.id):  # type: ignore[union-attr]
            return
        await message.answer("📊 Продажи (v1.1)")

    @router.message(F.text == "🗂 Категории")
    async def list_categories(message: Message) -> None:
        if not is_admin(message.from_user.id):  # type: ignore[union-attr]
            return
        categories = await service.get_categories(db)
        if not categories:
            await message.answer("Нет категорий.")
            return
        text = "🗂 Категории:\n" + "\n".join(
            f"• {c['name']} (ID: {c['id']})" for c in categories
        )
        await message.answer(text)

    return router
