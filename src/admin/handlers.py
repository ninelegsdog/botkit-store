from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from src.core.bot_factory import AppState
from src.core.fsm import AdminAuth
from src.core.nav import admin_menu, client_menu
from src.store import service


def create_admin_router(state: AppState) -> Router:
    router = Router()
    db = state.db

    def is_admin(user_id: int) -> bool:
        return user_id == 123456789  # TODO: real admin check

    @router.message(Command("admin"))
    async def cmd_admin(message: Message, state_fsm: FSMContext) -> None:
        await state_fsm.set_state(AdminAuth.waiting_password)
        await message.answer("🔑 Введите пароль:")

    @router.message(AdminAuth.waiting_password)
    async def check_password(message: Message, state_fsm: FSMContext) -> None:
        if message.text == state.config.admin_password:
            await state_fsm.clear()
            await message.answer("✅ Добро пожаловать!", reply_markup=admin_menu())
        else:
            await state_fsm.clear()
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
