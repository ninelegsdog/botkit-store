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
