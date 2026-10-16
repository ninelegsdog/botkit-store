from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from src.core.bot_factory import AppState
from src.core.callbacks import parse_callback_int
from src.core.navigation import client_menu
from src.core.ui import escape, order_card, product_card
from src.store import service


def create_store_router(app_state: AppState) -> Router:
    router = Router()
    db = app_state.db

    @router.message(Command("start"))
    async def cmd_start(message: Message, state: FSMContext) -> None:
        await state.clear()
        await message.answer(
            "🛍 Добро пожаловать в магазин!",
            reply_markup=client_menu(),
        )

    @router.message(F.text == "🛍 Каталог")
    async def show_catalog(message: Message) -> None:
        categories = await service.get_categories(db)
        if not categories:
            await message.answer("Каталог пуст.")
            return
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=c["name"], callback_data=f"store_cat:{c['id']}")]
                for c in categories
            ]
        )
        await message.answer("Выберите категорию:", reply_markup=kb)

    @router.callback_query(F.data.startswith("store_cat:"))
    async def show_category(callback: CallbackQuery) -> None:
        if not callback.data:
            return
        cat_id = parse_callback_int(callback.data, "store_cat:")
        if cat_id is None:
            await callback.answer("Некорректный запрос.", show_alert=True)
            return
        products = await service.get_products(db, cat_id)
        if not products:
            await callback.message.edit_text("Нет товаров.")  # type: ignore
            await callback.answer()
            return
        for p in products:
            card = product_card(p)
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(text="🛒 В корзину", callback_data=f"store_cart:{p['id']}"),
                        InlineKeyboardButton(text="💳 Купить", callback_data=f"store_buy:{p['id']}"),
                    ]
                ]
            )
            await callback.message.answer(card, reply_markup=kb)  # type: ignore
        await callback.answer()

    @router.callback_query(F.data.startswith("store_cart:"))
    async def add_to_cart(callback: CallbackQuery) -> None:
        if not callback.data:
            return
        product_id = parse_callback_int(callback.data, "store_cart:")
        if product_id is None:
            await callback.answer("Некорректный запрос.", show_alert=True)
            return
        await service.add_to_cart(db, callback.from_user.id, product_id)
        await callback.answer("✅ Добавлено в корзину!")

    @router.callback_query(F.data.startswith("store_buy:"))
    async def buy_now(callback: CallbackQuery, state: FSMContext) -> None:
        if not callback.data:
            return
        product_id = parse_callback_int(callback.data, "store_buy:")
        if product_id is None:
            await callback.answer("Некорректный запрос.", show_alert=True)
            return
        product = await service.get_product(db, product_id)
        if not product:
            await callback.answer("Товар не найден.", show_alert=True)
            return
        order_id = await service.create_order(
            db, callback.from_user.id, product_id, product["price"]
        )
        app_state.metrics.inc_orders()
        await callback.message.edit_text(  # type: ignore[union-attr]
            f"📦 Заказ #{order_id}\n"
            f"Товар: {escape(str(product.get('name', '')))}\n"
            f"Сумма: {product.get('price', 0)} Stars\n\n"
            f"Оплата через Telegram Stars."
        )
        await callback.answer()

    @router.message(F.text == "🛒 Корзина")
    async def show_cart(message: Message) -> None:
        items = await service.get_cart(db, message.from_user.id)  # type: ignore[union-attr]
        if not items:
            await message.answer("Корзина пуста.")
            return
        total = sum(item.get("price", 0) * item.get("qty", 1) for item in items)
        lines = ["🛒 Корзина:\n"]
        for item in items:
            name = escape(str(item.get("name", "")))
            qty = item.get("qty", 1)
            price = item.get("price", 0) * qty
            lines.append(f"• {name} x{qty} = {price} Stars")
        lines.append(f"\n💰 Итого: {total} Stars")
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✅ Оформить", callback_data="store_checkout")],
            ]
        )
        await message.answer("\n".join(lines), reply_markup=kb)

    @router.callback_query(F.data == "store_checkout")
    async def checkout(callback: CallbackQuery) -> None:
        items = await service.get_cart(db, callback.from_user.id)
        if not items:
            await callback.answer("Корзина пуста.", show_alert=True)
            return
        # Оформление — настоящий заказ по каждой позиции: раньше кнопка только
        # печатала «Оформление заказа», заказ не создавался и корзина не чистилась.
        order_ids = []
        total = 0
        for item in items:
            amount = item.get("price", 0) * item.get("qty", 1)
            order_id = await service.create_order(
                db, callback.from_user.id, int(item["product_id"]), amount
            )
            order_ids.append(order_id)
            total += amount
            app_state.metrics.inc_orders()
        await service.clear_cart(db, callback.from_user.id)
        orders_line = ", ".join(f"#{oid}" for oid in order_ids)
        await callback.message.edit_text(  # type: ignore
            f"✅ Заказ оформлен: {orders_line}\n"
            f"Сумма: {total} Stars\n\n"
            "Оплата через Telegram Stars. Посмотреть — «📦 Мои покупки»."
        )
        await callback.answer()
        await callback.message.answer("Выберите действие:", reply_markup=client_menu())  # type: ignore

    @router.message(F.text == "📦 Мои покупки")
    async def my_orders(message: Message) -> None:
        orders = await service.get_user_orders(db, message.from_user.id)  # type: ignore[union-attr]
        if not orders:
            await message.answer("Нет покупок.")
            return
        for o in orders[:10]:
            card = order_card(o)
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="📥 Получить товар",
                            callback_data=f"store_redeliver:{o['id']}",
                        )
                    ]
                ]
            )
            await message.answer(card, reply_markup=kb)

    @router.callback_query(F.data.startswith("store_redeliver:"))
    async def redeliver(callback: CallbackQuery) -> None:
        if not callback.data:
            return
        # Callback data is entirely client-controlled and order ids are sequential,
        # so the owner is part of the lookup. See service.get_delivery.
        order_id = parse_callback_int(callback.data, "store_redeliver:")
        if order_id is None:
            await callback.answer("Некорректный запрос.", show_alert=True)
            return
        delivery = await service.get_delivery(db, order_id, callback.from_user.id)
        if delivery:
            await callback.message.answer(f"📥 Ваш товар:\n{delivery['payload']}")  # type: ignore
        else:
            # One message for "no such order" and "not your order" alike: telling them
            # apart turns this into an oracle for which order ids exist.
            await callback.answer("Товар ещё не выдан.", show_alert=True)
        await callback.answer()

    return router
