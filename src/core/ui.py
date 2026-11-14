from __future__ import annotations

import html
from typing import Any


def escape(text: str | None) -> str:
    return html.escape(str(text)) if text else ""


def product_card(product: dict[str, Any]) -> str:
    lines = [
        f"📦 {escape(str(product.get('name', '')))}",
        f"💰 {product.get('price', 0)} Stars",
    ]
    if product.get("description"):
        lines.append(f"📝 {escape(str(product['description']))}")
    available = product.get("available_keys")
    if available is not None:
        lines.append(f"🔑 Остаток ключей: {available}")
    return "\n".join(lines)


def order_card(order: dict[str, Any]) -> str:
    status = str(order.get("status", "created"))
    status_emoji = {
        "created": "🆕",
        "pending_payment": "⏳",
        "paid": "💰",
        "delivered": "✅",
        "cancelled": "❌",
        "refunded": "💸",
    }.get(status, "❓")
    return (
        f"📦 Заказ #{order['id']}\n"
        f"Статус: {status_emoji} {status}\n"
        f"Сумма: {order.get('amount', 0)} Stars"
    )


def admin_product_card(product: dict[str, Any]) -> str:
    """Карточка товара для админа с остатком ключей и статусом активности."""
    active = "✅" if product.get("is_active") else "❌"
    lines = [
        f"{active} {escape(str(product.get('name', '')))} (ID: {product.get('id')})",
        f"💰 {product.get('price', 0)} Stars",
    ]
    if product.get("description"):
        lines.append(f"📝 {escape(str(product['description']))}")
    available = product.get("available_keys")
    if available is not None:
        total = product.get("total_keys", 0)
        lines.append(f"🔑 Ключи: {available} из {total}")
    return "\n".join(lines)


def admin_category_card(category: dict[str, Any]) -> str:
    """Карточка категории для админа с количеством товаров."""
    active = "✅" if category.get("is_active") else "❌"
    return (
        f"{active} {escape(str(category.get('name', '')))} (ID: {category.get('id')})\n"
        f"Товаров: {category.get('product_count', 0)}\n"
        f"Позиция: {category.get('position', 0)}"
    )


def admin_order_card(order: dict[str, Any]) -> str:
    """Карточка заказа для админа."""
    status = str(order.get("status", "created"))
    status_emoji = {
        "created": "🆕",
        "pending_payment": "⏳",
        "paid": "💰",
        "delivered": "✅",
        "cancelled": "❌",
        "refunded": "💸",
    }.get(status, "❓")
    return (
        f"📦 Заказ #{order['id']}\n"
        f"Статус: {status_emoji} {status}\n"
        f"Товар: {escape(str(order.get('product_name', '-')))}\n"
        f"Сумма: {order.get('amount', 0)} Stars\n"
        f"Покупатель: {order.get('user_id', '-')}"
    )


def sales_stats_text(stats: dict[str, int], period: str = "день") -> str:
    """Текст статистики продаж для админа."""
    return (
        f"📊 Продажи за {period}:\n\n"
        f"Оплачено заказов: {stats.get('paid_count', 0)}\n"
        f"Доставлено: {stats.get('delivered_count', 0)}\n"
        f"Выручка: {stats.get('revenue', 0)} Stars\n"
        f"Возвращено: {stats.get('refunded_count', 0)}"
    )
