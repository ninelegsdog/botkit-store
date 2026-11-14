from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from src.store import texts


@dataclass(frozen=True)
class NavSection:
    slug: str
    title: str


class NavRegistry:
    def __init__(self) -> None:
        self._sections: dict[str, NavSection] = {}

    def register(self, section: NavSection) -> None:
        self._sections[section.slug] = section

    def get(self, slug: str) -> NavSection | None:
        return self._sections.get(slug)

    def title(self, slug: str) -> str:
        section = self.get(slug)
        return section.title if section else slug

    def breadcrumbs(self, slug: str) -> list[str]:
        return [self.title(slug)]


def client_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=texts.BTN_CATALOG), KeyboardButton(text=texts.BTN_CART)],
            [KeyboardButton(text=texts.BTN_MY_ORDERS)],
        ],
        resize_keyboard=True,
    )


def admin_menu() -> ReplyKeyboardMarkup:
    """Главное админ-меню (reply)."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=texts.BTN_PRODUCTS), KeyboardButton(text=texts.BTN_CATEGORIES)],
            [KeyboardButton(text=texts.BTN_ORDERS), KeyboardButton(text=texts.BTN_SALES)],
            [KeyboardButton(text=texts.BTN_STOCK_LOW)],
        ],
        resize_keyboard=True,
    )


# ── Админ-клавиатуры (inline) ────────────────────────────────────────────────


def admin_categories_keyboard(categories: list[dict[str, Any]]) -> InlineKeyboardMarkup:
    """Список категорий для админа.

    Каждая строка: имя категории (открыть карточку) + кнопка «+ товар»
    для быстрого добавления товара в эту категорию.
    """
    rows: list[list[InlineKeyboardButton]] = []
    for c in categories:
        mark = "✅" if c["is_active"] else "❌"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{mark} {c['name']} ({c['product_count']})",
                    callback_data=f"admin_cat:{c['id']}",
                ),
                InlineKeyboardButton(
                    text="➕",
                    callback_data=f"admin_cat_add_prod:{c['id']}",
                ),
            ]
        )
    rows.append(
        [InlineKeyboardButton(text=texts.BTN_ADMIN_CAT_ADD, callback_data="admin_cat_add")]
    )
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_category_actions_keyboard(category_id: int) -> InlineKeyboardMarkup:
    """Действия с категорию: посмотреть товары, редактировать, переключить, удалить."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🛍 Товары категории",
                    callback_data=f"admin_cat_prods:{category_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text=texts.BTN_ADMIN_EDIT,
                    callback_data=f"admin_cat_edit:{category_id}",
                ),
                InlineKeyboardButton(
                    text=texts.BTN_ADMIN_TOGGLE,
                    callback_data=f"admin_cat_toggle:{category_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=texts.BTN_ADMIN_DEL,
                    callback_data=f"admin_cat_del:{category_id}",
                )
            ],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_cat_list")],
        ]
    )


def admin_products_keyboard(products: list[dict[str, Any]]) -> InlineKeyboardMarkup:
    """Список товаров для админа: имя + цена + остаток ключей."""
    rows: list[list[InlineKeyboardButton]] = []
    for p in products:
        stock = p.get("available_keys", 0)
        mark = "✅" if p["is_active"] else "❌"
        rows.append(
            [
                InlineKeyboardButton(
                    text=(
                        f"{mark} {p['name']} — {p['price']} Stars "
                        f"(ostatok: {stock})"
                    ),
                    callback_data=f"admin_prod:{p['id']}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_cat_list")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_product_actions_keyboard(product_id: int) -> InlineKeyboardMarkup:
    """Действия с товаром: редактировать, переключить активность, пополнить ключи, удалить."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=texts.BTN_ADMIN_EDIT,
                    callback_data=f"admin_prod_edit:{product_id}",
                ),
                InlineKeyboardButton(
                    text=texts.BTN_ADMIN_TOGGLE,
                    callback_data=f"admin_prod_toggle:{product_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=texts.BTN_ADMIN_KEYS,
                    callback_data=f"admin_prod_keys:{product_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text=texts.BTN_ADMIN_DEL,
                    callback_data=f"admin_prod_del:{product_id}",
                )
            ],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_prod_list")],
        ]
    )


def admin_orders_keyboard(orders: list[dict[str, Any]]) -> InlineKeyboardMarkup:
    """Список заказов для админа: номер, статус, сумма."""
    rows: list[list[InlineKeyboardButton]] = []
    for o in orders:
        status_emoji = {
            "created": "🆕",
            "pending_payment": "⏳",
            "paid": "💰",
            "delivered": "✅",
            "cancelled": "❌",
            "refunded": "💸",
        }.get(o["status"], "❓")
        rows.append(
            [
                InlineKeyboardButton(
                    text=(
                        f"#{o['id']} {status_emoji} {o['amount']} Stars — "
                        f"{o.get('product_name', '-')}"
                    ),
                    callback_data=f"admin_order:{o['id']}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_order_actions_keyboard(order_id: int, status: str) -> InlineKeyboardMarkup:
    """Действия с заказом в зависимости от статуса."""
    rows: list[list[InlineKeyboardButton]] = []
    if status == "paid":
        rows.append(
            [
                InlineKeyboardButton(
                    text=texts.BTN_ADMIN_FULFILL,
                    callback_data=f"admin_order_fulfill:{order_id}",
                )
            ]
        )
    if status in ("created", "pending_payment"):
        rows.append(
            [
                InlineKeyboardButton(
                    text=texts.BTN_ADMIN_CANCEL,
                    callback_data=f"admin_order_cancel:{order_id}",
                )
            ]
        )
    if status in ("paid", "delivered"):
        rows.append(
            [
                InlineKeyboardButton(
                    text=texts.BTN_ADMIN_REFUND,
                    callback_data=f"admin_order_refund:{order_id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_order_list")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_confirm_keyboard(action: str, item_id: int) -> InlineKeyboardMarkup:
    """Подтверждение destruктивного действия (удалить/отменить/вернуть)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Да", callback_data=f"admin_confirm:{action}:{item_id}"
                ),
                InlineKeyboardButton(text="❌ Нет", callback_data="admin_cancel_confirm"),
            ]
        ]
    )
