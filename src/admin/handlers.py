from __future__ import annotations

from typing import Any

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from src.core.auth import AdminGate
from src.core.bot_factory import AppState
from src.core.callbacks import parse_callback_int
from src.core.fsm import AdminAuth, AdminCategory, AdminOrder, AdminProduct
from src.core.navigation import (
    admin_categories_keyboard,
    admin_category_actions_keyboard,
    admin_confirm_keyboard,
    admin_menu,
    admin_order_actions_keyboard,
    admin_orders_keyboard,
    admin_product_actions_keyboard,
    admin_products_keyboard,
)
from src.core.ui import (
    admin_category_card,
    admin_order_card,
    admin_product_card,
    sales_stats_text,
)
from src.store import service, texts


def create_admin_router(app_state: AppState) -> Router:
    router = Router()
    db = app_state.db
    gate = AdminGate(
        app_state.config.admin_password, app_state.config.admin_ids or []
    )

    def is_admin(user_id: int) -> bool:
        return gate.is_admin(user_id)

    # ── Вход в админку ──────────────────────────────────────────────────────

    @router.message(Command("admin"))
    async def cmd_admin(message: Message, state: FSMContext) -> None:
        await state.set_state(AdminAuth.waiting_password)
        await message.answer(texts.ASK_PASSWORD)

    @router.message(AdminAuth.waiting_password)
    async def check_password(message: Message, state: FSMContext) -> None:
        user_id = message.from_user.id  # type: ignore[union-attr]
        if gate.is_throttled(user_id):
            await state.clear()
            await message.answer(
                texts.TOO_MANY_ATTEMPTS,
                reply_markup=admin_menu(),
            )
            return
        if gate.authorize(user_id, message.text or ""):
            await state.clear()
            await message.answer(texts.ADMIN_WELCOME, reply_markup=admin_menu())
        else:
            await state.clear()
            await message.answer(texts.BAD_PASSWORD, reply_markup=admin_menu())

    # ── Категории ───────────────────────────────────────────────────────────

    @router.message(F.text == "🗂 Категории")
    async def list_categories(message: Message) -> None:
        if not is_admin(message.from_user.id):  # type: ignore[union-attr]
            return
        categories = await service.get_categories_admin(db)
        if not categories:
            await message.answer(texts.ADMIN_CAT_EMPTY, reply_markup=admin_menu())
            return
        await message.answer(
            texts.CATEGORIES_HEADER,
            reply_markup=admin_categories_keyboard(categories),
        )

    @router.callback_query(F.data == "admin_cat_list")
    async def cb_cat_list(callback: CallbackQuery) -> None:
        categories = await service.get_categories_admin(db)
        if not categories:
            await callback.message.edit_text(texts.ADMIN_CAT_EMPTY)  # type: ignore[union-attr]
            await callback.answer()
            return
        await callback.message.edit_text(  # type: ignore[union-attr]
            texts.CATEGORIES_HEADER,
            reply_markup=admin_categories_keyboard(categories),
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("admin_cat:"))
    async def cb_cat_open(callback: CallbackQuery) -> None:
        if not callback.data:
            return
        cat_id = parse_callback_int(callback.data, "admin_cat:")
        if cat_id is None:
            await callback.answer(texts.BAD_REQUEST, show_alert=True)
            return
        categories = await service.get_categories_admin(db)
        cat = next((c for c in categories if c["id"] == cat_id), None)
        if cat is None:
            await callback.answer(texts.PRODUCT_NOT_FOUND, show_alert=True)
            return
        await callback.message.edit_text(  # type: ignore[union-attr]
            admin_category_card(cat),
            reply_markup=admin_category_actions_keyboard(cat_id),
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("admin_cat_prods:"))
    async def cb_cat_prods(callback: CallbackQuery) -> None:
        if not callback.data:
            return
        cat_id = parse_callback_int(callback.data, "admin_cat_prods:")
        if cat_id is None:
            await callback.answer(texts.BAD_REQUEST, show_alert=True)
            return
        products = await service.get_products(db, cat_id)
        if not products:
            await callback.message.edit_text(  # type: ignore[union-attr]
                texts.ADMIN_PROD_EMPTY,
                reply_markup=admin_category_actions_keyboard(cat_id),
            )
            await callback.answer()
            return
        for p in products:
            stock = await service.get_stock(db, p["id"])
            p["available_keys"] = stock["available"]
            p["total_keys"] = stock["total"]
        await callback.message.edit_text(  # type: ignore[union-attr]
            "Товары категории:",
            reply_markup=admin_products_keyboard(products),
        )
        await callback.answer()

    @router.callback_query(F.data == "admin_cat_add")
    async def cb_cat_add(callback: CallbackQuery, state: FSMContext) -> None:
        await state.set_state(AdminCategory.entering_name)
        await state.update_data(cat_action="create")
        await callback.message.edit_text(  # type: ignore[union-attr]
            "Введите название категории:"
        )
        await callback.answer()

    @router.message(AdminCategory.entering_name)
    async def cat_enter_name(message: Message, state: FSMContext) -> None:
        name = (message.text or "").strip()
        if not name:
            await message.answer("Название не может быть пустым. Попробуйте ещё раз:")
            return
        await state.update_data(cat_name=name)
        await state.set_state(AdminCategory.entering_position)
        await message.answer("Введите позицию (целое число, сортировка):")

    @router.message(AdminCategory.entering_position)
    async def cat_enter_position(message: Message, state: FSMContext) -> None:
        try:
            position = int((message.text or "").strip())
        except (ValueError, TypeError):
            await message.answer(texts.ERR_INVALID_POSITION)
            return
        data = await state.get_data()
        cat_name = data.get("cat_name", "")
        cat_id = data.get("cat_id")
        action = data.get("cat_action")
        if action == "edit" and cat_id:
            await service.update_category(db, cat_id, name=cat_name, position=position)
            await state.clear()
            await message.answer(
                texts.ADMIN_CAT_UPDATED,
                reply_markup=admin_menu(),
            )
        else:
            await service.create_category(db, cat_name)
            categories = await service.get_categories_admin(db)
            new_cat = next((c for c in categories if c["name"] == cat_name), None)
            if new_cat:
                await service.update_category(db, new_cat["id"], position=position)
            await state.clear()
            await message.answer(
                texts.ADMIN_CAT_CREATED.format(name=cat_name),
                reply_markup=admin_menu(),
            )

    @router.callback_query(F.data.startswith("admin_cat_edit:"))
    async def cb_cat_edit(callback: CallbackQuery, state: FSMContext) -> None:
        if not callback.data:
            return
        cat_id = parse_callback_int(callback.data, "admin_cat_edit:")
        if cat_id is None:
            await callback.answer(texts.BAD_REQUEST, show_alert=True)
            return
        await state.set_state(AdminCategory.entering_name)
        await state.update_data(cat_action="edit", cat_id=cat_id)
        await callback.message.edit_text(  # type: ignore[union-attr]
            "Введите новое название категории (или '-' для пропуска):"
        )
        await callback.answer()

    @router.message(AdminCategory.entering_name)
    async def cat_edit_enter_name(message: Message, state: FSMContext) -> None:
        name = (message.text or "").strip()
        data = await state.get_data()
        cat_id = data.get("cat_id")
        if name == "-":
            # Skip name edit, go to position or finish
            if data.get("cat_action") == "edit" and cat_id:
                await state.clear()
                await message.answer(
                    texts.ADMIN_CAT_UPDATED,
                    reply_markup=admin_menu(),
                )
            return
        if not name:
            await message.answer("Название не может быть пустым. Попробуйте ещё раз:")
            return
        await state.update_data(cat_name=name)
        await state.set_state(AdminCategory.entering_position)
        await message.answer("Введите позицию (целое число, сортировка):")

    @router.callback_query(F.data.startswith("admin_cat_toggle:"))
    async def cb_cat_toggle(callback: CallbackQuery) -> None:
        if not callback.data:
            return
        cat_id = parse_callback_int(callback.data, "admin_cat_toggle:")
        if cat_id is None:
            await callback.answer(texts.BAD_REQUEST, show_alert=True)
            return
        new_value = await service.toggle_category(db, cat_id)
        if new_value is None:
            await callback.answer(texts.PRODUCT_NOT_FOUND, show_alert=True)
            return
        await callback.answer(texts.ADMIN_CAT_TOGGLED)
        await cb_cat_list(callback)

    @router.callback_query(F.data.startswith("admin_cat_del:"))
    async def cb_cat_del(callback: CallbackQuery) -> None:
        if not callback.data:
            return
        cat_id = parse_callback_int(callback.data, "admin_cat_del:")
        if cat_id is None:
            await callback.answer(texts.BAD_REQUEST, show_alert=True)
            return
        await callback.message.edit_text(  # type: ignore[union-attr]
            "Удалить категорию? Она станет невидимой, товары останутся.",
            reply_markup=admin_confirm_keyboard("cat_del", cat_id),
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("admin_confirm:cat_del:"))
    async def cb_confirm_cat_del(callback: CallbackQuery) -> None:
        if not callback.data:
            return
        cat_id = parse_callback_int(callback.data, "admin_confirm:cat_del:")
        if cat_id is None:
            await callback.answer(texts.BAD_REQUEST, show_alert=True)
            return
        ok = await service.delete_category(db, cat_id)
        if ok:
            await callback.message.edit_text(texts.ADMIN_CAT_DELETED)  # type: ignore[union-attr]
        else:
            await callback.message.edit_text(texts.ADMIN_CAT_CANNOT_DELETE)  # type: ignore[union-attr]
        await callback.answer()

    # ── Товары ──────────────────────────────────────────────────────────────

    @router.message(F.text == "🛍 Товары")
    async def list_products(message: Message) -> None:
        if not is_admin(message.from_user.id):  # type: ignore[union-attr]
            return
        categories = await service.get_categories_admin(db)
        if not categories:
            await message.answer(texts.ADMIN_CAT_EMPTY, reply_markup=admin_menu())
            return
        await message.answer(
            "Выберите категорию для просмотра товаров:",
            reply_markup=admin_categories_keyboard(categories),
        )

    @router.callback_query(F.data == "admin_prod_list")
    async def cb_prod_list(callback: CallbackQuery) -> None:
        categories = await service.get_categories_admin(db)
        all_products: list[dict[str, Any]] = []
        for c in categories:
            products = await service.get_products(db, c["id"])
            for p in products:
                p["category_name"] = c["name"]
                all_products.append(p)
        if not all_products:
            await callback.message.edit_text(texts.ADMIN_PROD_EMPTY)  # type: ignore[union-attr]
            await callback.answer()
            return
        await callback.message.edit_text(  # type: ignore[union-attr]
            "Все товары:",
            reply_markup=admin_products_keyboard(all_products),
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("admin_prod:"))
    async def cb_prod_open(callback: CallbackQuery) -> None:
        if not callback.data:
            return
        prod_id = parse_callback_int(callback.data, "admin_prod:")
        if prod_id is None:
            await callback.answer(texts.BAD_REQUEST, show_alert=True)
            return
        product = await service.get_product_admin(db, prod_id)
        if product is None:
            await callback.answer(texts.PRODUCT_NOT_FOUND, show_alert=True)
            return
        stock = await service.get_stock(db, prod_id)
        product["available_keys"] = stock["available"]
        product["total_keys"] = stock["total"]
        await callback.message.edit_text(  # type: ignore[union-attr]
            admin_product_card(product),
            reply_markup=admin_product_actions_keyboard(prod_id),
        )
        await callback.answer()

    # Start product creation from a specific category
    @router.callback_query(F.data.startswith("admin_cat_add_prod:"))
    async def cb_prod_add_start(callback: CallbackQuery, state: FSMContext) -> None:
        if not callback.data:
            return
        cat_id = parse_callback_int(callback.data, "admin_cat_add_prod:")
        if cat_id is None:
            await callback.answer(texts.BAD_REQUEST, show_alert=True)
            return
        await state.set_state(AdminProduct.entering_name)
        await state.update_data(prod_action="create", cat_id=cat_id)
        await callback.message.edit_text(  # type: ignore[union-attr]
            "Введите название товара:"
        )
        await callback.answer()

    @router.message(AdminProduct.entering_name)
    async def prod_enter_name(message: Message, state: FSMContext) -> None:
        name = (message.text or "").strip()
        if not name:
            await message.answer("Название не может быть пустым. Попробуйте ещё раз:")
            return
        await state.update_data(prod_name=name)
        await state.set_state(AdminProduct.entering_description)
        await message.answer("Введите описание товара (или '-' для пропуска):")

    @router.message(AdminProduct.entering_description)
    async def prod_enter_description(message: Message, state: FSMContext) -> None:
        desc = (message.text or "").strip()
        if desc == "-":
            desc = ""
        await state.update_data(prod_description=desc)
        await state.set_state(AdminProduct.entering_price)
        await message.answer("Введите цену в Stars (целое число > 0):")

    @router.message(AdminProduct.entering_price)
    async def prod_enter_price(message: Message, state: FSMContext) -> None:
        try:
            price = int((message.text or "").strip())
        except (ValueError, TypeError):
            await message.answer(texts.ERR_INVALID_PRICE)
            return
        if price <= 0:
            await message.answer(texts.ERR_INVALID_PRICE)
            return
        await state.update_data(prod_price=price)
        await state.set_state(AdminProduct.entering_delivery_type)
        await message.answer(
            "Тип выдачи:\n1 — текст (ключ из пула)\n2 — ссылка\n3 — файл\n\n"
            "Введите 1, 2 или 3:"
        )

    @router.message(AdminProduct.entering_delivery_type)
    async def prod_enter_delivery_type(message: Message, state: FSMContext) -> None:
        choice = (message.text or "").strip()
        mapping = {"1": "text", "2": "link", "3": "file"}
        if choice not in mapping:
            await message.answer("Введите 1, 2 или 3:")
            return
        await state.update_data(prod_delivery_type=mapping[choice])
        delivery_type = mapping[choice]
        if delivery_type == "text":
            await state.set_state(AdminProduct.entering_keys_batch)
            await message.answer(
                "Введите ключи по одной строке (каждая строка — отдельный ключ).\n"
                "Отправьте пустое сообщение, если ключи будут добавлены позже."
            )
        elif delivery_type == "link":
            await state.set_state(AdminProduct.entering_delivery_payload)
            await message.answer("Введите ссылку (URL) для выдачи:")
        else:  # file
            await state.set_state(AdminProduct.entering_photo)
            await message.answer(
                "Отправьте файл (документ) — его file_id будет использован для выдачи.\n"
                "Или отправьте '-' чтобы пропустить."
            )

    @router.message(AdminProduct.entering_keys_batch)
    async def prod_enter_keys(message: Message, state: FSMContext) -> None:
        text_input = message.text or ""
        if text_input.strip() == "":
            keys: list[str] = []
        else:
            keys = [line.strip() for line in text_input.splitlines() if line.strip()]
        await state.update_data(prod_keys=keys)
        await state.set_state(AdminProduct.entering_photo)
        await message.answer(
            "Отправьте фото товара (file_id) или '-' для пропуска:"
        )

    @router.message(AdminProduct.entering_delivery_payload)
    async def prod_enter_payload_link(message: Message, state: FSMContext) -> None:
        payload = (message.text or "").strip()
        if not payload:
            await message.answer("Ссылка не может быть пустой. Попробуйте ещё раз:")
            return
        await state.update_data(prod_delivery_payload=payload, prod_keys=[])
        await state.set_state(AdminProduct.entering_photo)
        await message.answer("Отправьте фото товара (file_id) или '-' для пропуска:")

    @router.message(AdminProduct.entering_photo)
    async def prod_enter_photo(message: Message, state: FSMContext) -> None:
        photo = (message.text or "").strip()
        if photo == "-":
            photo = ""
        data = await state.get_data()
        cat_id = data.get("cat_id")
        if cat_id is None:
            await state.clear()
            await message.answer(
                "Ошибка: категория не выбрана.", reply_markup=admin_menu()
            )
            return
        prod_id = await service.create_product(
            db,
            category_id=cat_id,
            name=data.get("prod_name", ""),
            description=data.get("prod_description", ""),
            price=int(data.get("prod_price", 0)),
            delivery_type=data.get("prod_delivery_type", "text"),
            delivery_payload=data.get("prod_delivery_payload", ""),
            photo_file_id=photo,
        )
        keys = data.get("prod_keys", [])
        if keys:
            await service.add_keys(db, prod_id, keys)
        await state.clear()
        await message.answer(
            texts.ADMIN_PROD_CREATED.format(
                name=data.get("prod_name", ""),
                price=int(data.get("prod_price", 0)),
            ),
            reply_markup=admin_menu(),
        )

    @router.callback_query(F.data.startswith("admin_prod_edit:"))
    async def cb_prod_edit(callback: CallbackQuery, state: FSMContext) -> None:
        if not callback.data:
            return
        prod_id = parse_callback_int(callback.data, "admin_prod_edit:")
        if prod_id is None:
            await callback.answer(texts.BAD_REQUEST, show_alert=True)
            return
        await state.set_state(AdminProduct.entering_name)
        await state.update_data(prod_action="edit", prod_id=prod_id)
        await callback.message.edit_text(  # type: ignore[union-attr]
            "Введите новое название товара (или '-' для пропуска):"
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("admin_prod_toggle:"))
    async def cb_prod_toggle(callback: CallbackQuery) -> None:
        if not callback.data:
            return
        prod_id = parse_callback_int(callback.data, "admin_prod_toggle:")
        if prod_id is None:
            await callback.answer(texts.BAD_REQUEST, show_alert=True)
            return
        new_value = await service.toggle_product(db, prod_id)
        if new_value is None:
            await callback.answer(texts.PRODUCT_NOT_FOUND, show_alert=True)
            return
        await callback.answer(texts.ADMIN_PROD_TOGGLED)
        await cb_prod_list(callback)

    @router.callback_query(F.data.startswith("admin_prod_keys:"))
    async def cb_prod_keys(callback: CallbackQuery, state: FSMContext) -> None:
        if not callback.data:
            return
        prod_id = parse_callback_int(callback.data, "admin_prod_keys:")
        if prod_id is None:
            await callback.answer(texts.BAD_REQUEST, show_alert=True)
            return
        await state.set_state(AdminProduct.entering_keys_batch)
        await state.update_data(prod_action="add_keys", prod_id=prod_id)
        await callback.message.edit_text(  # type: ignore[union-attr]
            "Введите ключи по одной строке (каждая строка — отдельный ключ):"
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("admin_prod_del:"))
    async def cb_prod_del(callback: CallbackQuery) -> None:
        if not callback.data:
            return
        prod_id = parse_callback_int(callback.data, "admin_prod_del:")
        if prod_id is None:
            await callback.answer(texts.BAD_REQUEST, show_alert=True)
            return
        await callback.message.edit_text(  # type: ignore[union-attr]
            "Удалить товар? Нельзя удалить товар с активными заказами.",
            reply_markup=admin_confirm_keyboard("prod_del", prod_id),
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("admin_confirm:prod_del:"))
    async def cb_confirm_prod_del(callback: CallbackQuery) -> None:
        if not callback.data:
            return
        prod_id = parse_callback_int(callback.data, "admin_confirm:prod_del:")
        if prod_id is None:
            await callback.answer(texts.BAD_REQUEST, show_alert=True)
            return
        ok = await service.delete_product(db, prod_id)
        if ok:
            await callback.message.edit_text(texts.ADMIN_PROD_DELETED)  # type: ignore[union-attr]
        else:
            await callback.message.edit_text(texts.ADMIN_PROD_CANNOT_DELETE)  # type: ignore[union-attr]
        await callback.answer()

    # ── Заказы ──────────────────────────────────────────────────────────────

    @router.message(F.text == "📦 Заказы")
    async def list_orders(message: Message) -> None:
        if not is_admin(message.from_user.id):  # type: ignore[union-attr]
            return
        orders = await service.get_orders_by_status(db, limit=50)
        if not orders:
            await message.answer(texts.ADMIN_ORDER_EMPTY, reply_markup=admin_menu())
            return
        await message.answer(
            "Последние заказы:",
            reply_markup=admin_orders_keyboard(orders),
        )

    @router.callback_query(F.data == "admin_order_list")
    async def cb_order_list(callback: CallbackQuery) -> None:
        orders = await service.get_orders_by_status(db, limit=50)
        if not orders:
            await callback.message.edit_text(texts.ADMIN_ORDER_EMPTY)  # type: ignore[union-attr]
            await callback.answer()
            return
        await callback.message.edit_text(  # type: ignore[union-attr]
            "Последние заказы:",
            reply_markup=admin_orders_keyboard(orders),
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("admin_order:"))
    async def cb_order_open(callback: CallbackQuery) -> None:
        if not callback.data:
            return
        order_id = parse_callback_int(callback.data, "admin_order:")
        if order_id is None:
            await callback.answer(texts.BAD_REQUEST, show_alert=True)
            return
        orders = await service.get_orders_by_status(db, limit=1000)
        order = next((o for o in orders if o["id"] == order_id), None)
        if order is None:
            await callback.answer(texts.ADMIN_ORDER_NOT_FOUND, show_alert=True)
            return
        await callback.message.edit_text(  # type: ignore[union-attr]
            admin_order_card(order),
            reply_markup=admin_order_actions_keyboard(order_id, order["status"]),
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("admin_order_fulfill:"))
    async def cb_order_fulfill(callback: CallbackQuery, state: FSMContext) -> None:
        if not callback.data:
            return
        order_id = parse_callback_int(callback.data, "admin_order_fulfill:")
        if order_id is None:
            await callback.answer(texts.BAD_REQUEST, show_alert=True)
            return
        await state.set_state(AdminOrder.confirming_fulfill)
        await state.update_data(order_id=order_id)
        await callback.message.edit_text(  # type: ignore[union-attr]
            "Введите текст/ключ/ссылку для выдачи покупателю:"
        )
        await callback.answer()

    @router.message(AdminOrder.confirming_fulfill)
    async def order_fulfill_enter(message: Message, state: FSMContext) -> None:
        payload = (message.text or "").strip()
        if not payload:
            await message.answer("Пayload не может быть пустым. Попробуйте ещё раз:")
            return
        data = await state.get_data()
        order_id = int(data["order_id"])
        ok = await service.manual_fulfill_order(db, order_id, payload)
        await state.clear()
        if ok:
            await message.answer(
                texts.ADMIN_ORDER_FULFILLED.format(order_id=order_id),
                reply_markup=admin_menu(),
            )
        else:
            await message.answer(texts.ADMIN_ORDER_NOT_FOUND, reply_markup=admin_menu())

    @router.callback_query(F.data.startswith("admin_order_cancel:"))
    async def cb_order_cancel(callback: CallbackQuery) -> None:
        if not callback.data:
            return
        order_id = parse_callback_int(callback.data, "admin_order_cancel:")
        if order_id is None:
            await callback.answer(texts.BAD_REQUEST, show_alert=True)
            return
        await callback.message.edit_text(  # type: ignore[union-attr]
            "Отменить заказ? Только неоплаченные заказы можно отменить.",
            reply_markup=admin_confirm_keyboard("order_cancel", order_id),
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("admin_confirm:order_cancel:"))
    async def cb_confirm_order_cancel(callback: CallbackQuery) -> None:
        if not callback.data:
            return
        order_id = parse_callback_int(callback.data, "admin_confirm:order_cancel:")
        if order_id is None:
            await callback.answer(texts.BAD_REQUEST, show_alert=True)
            return
        ok = await service.cancel_order(db, order_id)
        message = callback.message
        if isinstance(message, Message):
            if ok:
                await message.edit_text(
                    texts.ADMIN_ORDER_CANCELLED.format(order_id=order_id)
                )
            else:
                await message.edit_text(texts.ADMIN_ORDER_NOT_FOUND)
        await callback.answer()

    @router.callback_query(F.data.startswith("admin_order_refund:"))
    async def cb_order_refund(callback: CallbackQuery) -> None:
        if not callback.data:
            return
        order_id = parse_callback_int(callback.data, "admin_order_refund:")
        if order_id is None:
            await callback.answer(texts.BAD_REQUEST, show_alert=True)
            return
        await callback.message.edit_text(  # type: ignore[union-attr]
            "Вернуть деньги (Stars) и пометить заказ как возвращённый?",
            reply_markup=admin_confirm_keyboard("order_refund", order_id),
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("admin_confirm:order_refund:"))
    async def cb_confirm_order_refund(callback: CallbackQuery) -> None:
        if not callback.data:
            return
        order_id = parse_callback_int(callback.data, "admin_confirm:order_refund:")
        if order_id is None:
            await callback.answer(texts.BAD_REQUEST, show_alert=True)
            return
        ok = await service.refund_order(db, order_id)
        message = callback.message
        if isinstance(message, Message):
            if ok:
                await message.edit_text(
                    texts.ADMIN_ORDER_REFUNDED.format(order_id=order_id)
                )
            else:
                await message.edit_text(texts.ADMIN_ORDER_NOT_FOUND)
        await callback.answer()

    # ── Продажи ─────────────────────────────────────────────────────────────

    @router.message(F.text == "📊 Продажи")
    async def sales_stats(message: Message) -> None:
        if not is_admin(message.from_user.id):  # type: ignore[union-attr]
            return
        stats = await service.get_sales_stats(db, period="day")
        await message.answer(
            sales_stats_text(stats, period="день"),
            reply_markup=admin_menu(),
        )

    # ── Остатки ключей ──────────────────────────────────────────────────────

    @router.message(F.text == "⚠️ Остатки ключей")
    async def stock_low(message: Message) -> None:
        if not is_admin(message.from_user.id):  # type: ignore[union-attr]
            return
        low = await service.get_low_stock_products(db, threshold=5)
        if not low:
            await message.answer(texts.ADMIN_STOCK_EMPTY, reply_markup=admin_menu())
            return
        lines = ["⚠️ Товары с низким остатком ключей:\n"]
        for p in low:
            lines.append(f"• {p['name']} — {p['available_keys']} из {p['total_keys']}")
        await message.answer("\n".join(lines), reply_markup=admin_menu())

    # ── Подтверждения / навигация ───────────────────────────────────────────

    @router.callback_query(F.data == "admin_cancel_confirm")
    async def cb_cancel_confirm(callback: CallbackQuery) -> None:
        await callback.answer("Отменено")

    @router.callback_query(F.data == "admin_back")
    async def cb_admin_back(callback: CallbackQuery) -> None:
        await callback.message.answer(  # type: ignore[union-attr]
            "Админ-меню. Выберите раздел:", reply_markup=admin_menu()
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("admin_confirm:"))
    async def cb_admin_confirm_general(callback: CallbackQuery) -> None:
        """General confirm handler for contract compliance."""
        await callback.answer("Подтверждено")

    return router
