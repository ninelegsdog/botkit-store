from __future__ import annotations

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


def client_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🛍 Каталог"), KeyboardButton(text="🛒 Корзина")],
            [KeyboardButton(text="📦 Мои покупки")],
        ],
        resize_keyboard=True,
    )


def admin_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🛍 Товары"), KeyboardButton(text="🗂 Категории")],
            [KeyboardButton(text="📦 Заказы"), KeyboardButton(text="📊 Продажи")],
        ],
        resize_keyboard=True,
    )
