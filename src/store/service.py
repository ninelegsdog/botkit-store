from __future__ import annotations

from typing import Any

import httpx
from sqlalchemy import text

from src.core.database import Database


async def get_categories(db: Database) -> list[dict[str, Any]]:
    async with db.session() as session:
        result = await session.execute(
            text("SELECT * FROM categories WHERE is_active = 1 ORDER BY position")
        )
        return [dict(r) for r in result.mappings().all()]


async def get_products(db: Database, category_id: int) -> list[dict[str, Any]]:
    async with db.session() as session:
        result = await session.execute(
            text(
                "SELECT * FROM products WHERE category_id = :cid AND is_active = 1"
            ),
            {"cid": category_id},
        )
        return [dict(r) for r in result.mappings().all()]


async def get_product(db: Database, product_id: int) -> dict[str, Any] | None:
    async with db.session() as session:
        result = await session.execute(
            text("SELECT * FROM products WHERE id = :id"), {"id": product_id}
        )
        row = result.mappings().fetchone()
        return dict(row) if row else None


async def add_to_cart(db: Database, user_id: int, product_id: int) -> None:
    async with db.transaction() as session:
        existing = await session.execute(
            text("SELECT id FROM carts WHERE user_id = :uid AND product_id = :pid"),
            {"uid": user_id, "pid": product_id},
        )
        if existing.fetchone():
            await session.execute(
                text(
                    "UPDATE carts SET qty = qty + 1 WHERE user_id = :uid AND product_id = :pid"
                ),
                {"uid": user_id, "pid": product_id},
            )
        else:
            await session.execute(
                text("INSERT INTO carts (user_id, product_id, qty) VALUES (:uid, :pid, 1)"),
                {"uid": user_id, "pid": product_id},
            )


async def get_cart(db: Database, user_id: int) -> list[dict[str, Any]]:
    async with db.session() as session:
        result = await session.execute(
            text(
                "SELECT c.*, p.name, p.price FROM carts c "
                "JOIN products p ON c.product_id = p.id "
                "WHERE c.user_id = :uid"
            ),
            {"uid": user_id},
        )
        return [dict(r) for r in result.mappings().all()]


async def remove_from_cart(db: Database, user_id: int, product_id: int) -> None:
    async with db.transaction() as session:
        await session.execute(
            text("DELETE FROM carts WHERE user_id = :uid AND product_id = :pid"),
            {"uid": user_id, "pid": product_id},
        )


async def clear_cart(db: Database, user_id: int) -> None:
    async with db.transaction() as session:
        await session.execute(
            text("DELETE FROM carts WHERE user_id = :uid"), {"uid": user_id}
        )


async def create_order(
    db: Database, user_id: int, product_id: int, amount: int
) -> int:
    async with db.transaction() as session:
        result = await session.execute(
            text(
                "INSERT INTO orders (user_id, product_id, amount, status) "
                "VALUES (:uid, :pid, :amt, 'pending_payment')"
            ),
            {"uid": user_id, "pid": product_id, "amt": amount},
        )
        order_id = result.lastrowid  # type: ignore[attr-defined]
        assert order_id is not None
        return int(order_id)


async def get_order(db: Database, order_id: int) -> dict[str, Any] | None:
    async with db.session() as session:
        result = await session.execute(
            text("SELECT * FROM orders WHERE id = :id"), {"id": order_id}
        )
        row = result.mappings().fetchone()
        return dict(row) if row else None


async def get_user_orders(db: Database, user_id: int) -> list[dict[str, Any]]:
    async with db.session() as session:
        result = await session.execute(
            text(
                "SELECT o.*, p.name FROM orders o "
                "JOIN products p ON o.product_id = p.id "
                "WHERE o.user_id = :uid ORDER BY o.created_at DESC"
            ),
            {"uid": user_id},
        )
        return [dict(r) for r in result.mappings().all()]


async def mark_paid(db: Database, order_id: int, payment_id: str) -> bool:
    """Record payment for an order, at most once.

    Returns True when this call is the one that transitioned the order, False when the
    order was already paid or does not exist.

    Telegram re-sends `successful_payment` whenever our answer to the previous one was
    lost - a timeout looks identical to a failure, so the bot gets the same update
    again. The original version had no guard at all: every replay rewrote the order and
    appended another `payments` row. Guarding the UPDATE makes the state change
    idempotent, and inserting the payment row only when the UPDATE actually claimed a
    row keeps the ledger at one entry per payment.
    """
    async with db.transaction() as session:
        result = await session.execute(
            text(
                "UPDATE orders SET status = 'paid', payment_id = :pid "
                "WHERE id = :oid AND status = 'pending_payment'"
            ),
            {"pid": payment_id, "oid": order_id},
        )
        if result.rowcount == 0:  # type: ignore[attr-defined]
            return False

        await session.execute(
            text(
                "INSERT INTO payments (order_id, provider, amount, status, external_id) "
                "VALUES (:oid, 'stars', (SELECT amount FROM orders WHERE id = :oid), "
                "'succeeded', :eid)"
            ),
            {"oid": order_id, "eid": payment_id},
        )
        return True


async def fulfill_order(db: Database, order_id: int) -> str | None:
    """Allocate one unused key for a paid order and record the delivery, once.

    Returns the key that was delivered, or None when the order was already fulfilled or
    no key is left in stock.

    Everything happens in one transaction and the status change is guarded, so two
    concurrent calls cannot both claim the order: the second UPDATE matches no rows and
    returns None. The previous `deliver_order(order_id, payload)` took an already
    allocated payload from the caller, which split "check the order is paid" and "give
    out the key" across two steps with a window between them.

    `use_key` had its own defect: it UPDATEd a free key to the user and then SELECTed
    `WHERE used_by = :uid` with no LIMIT, so a customer who bought the same product
    twice could be handed the key from their *first* purchase. RETURNING takes the exact
    row the UPDATE claimed, which is what we meant to do.
    """
    async with db.transaction() as session:
        result = await session.execute(
            text(
                "UPDATE orders SET status = 'delivered', delivered_at = datetime('now') "
                "WHERE id = :oid AND status = 'paid' RETURNING product_id"
            ),
            {"oid": order_id},
        )
        row = result.first()
        if row is None:
            return None
        product_id = int(row[0])

        key_result = await session.execute(
            text(
                "UPDATE keys SET used_by = (SELECT user_id FROM orders WHERE id = :oid), "
                "used_at = datetime('now') "
                "WHERE id = (SELECT id FROM keys WHERE product_id = :pid AND used_by IS NULL "
                "ORDER BY id LIMIT 1) RETURNING value"
            ),
            {"oid": order_id, "pid": product_id},
        )
        key_row = key_result.first()
        if key_row is None:
            # No stock left. Roll the status back so the order stays paid and can be
            # fulfilled later; leaving it 'delivered' with nothing delivered would hide
            # the problem from both the customer and get_order_stats.
            await session.execute(
                text(
                    "UPDATE orders SET status = 'paid', delivered_at = NULL WHERE id = :oid"
                ),
                {"oid": order_id},
            )
            return None

        await session.execute(
            text(
                "INSERT INTO product_deliveries (order_id, payload) VALUES (:oid, :p)"
            ),
            {"oid": order_id, "p": str(key_row[0])},
        )
        return str(key_row[0])


async def get_delivery(
    db: Database, order_id: int, user_id: int
) -> dict[str, Any] | None:
    """Read a delivered order, but only for the user who placed it.

    `user_id` is a required argument and part of the WHERE clause rather than a check
    in the handler. `order_id` arrives from `callback.data`, which the client fully
    controls, and ids are sequential integers - so a handler that filtered afterwards
    by `order['user_id']` would still have had to trust a value it had already read.
    Filtering in the query means a wrong or absent id returns nothing instead of
    another customer's payload.
    """
    async with db.session() as session:
        result = await session.execute(
            text(
                "SELECT d.* FROM product_deliveries d "
                "JOIN orders o ON o.id = d.order_id "
                "WHERE d.order_id = :oid AND o.user_id = :uid LIMIT 1"
            ),
            {"oid": order_id, "uid": user_id},
        )
        row = result.mappings().fetchone()
        return dict(row) if row else None


async def get_available_keys_count(db: Database, product_id: int) -> int:
    async with db.session() as session:
        result = await session.execute(
            text(
                "SELECT COUNT(*) as cnt FROM keys WHERE product_id = :pid AND used_by IS NULL"
            ),
            {"pid": product_id},
        )
        row = result.fetchone()
        return int(row[0]) if row else 0


async def create_category(db: Database, name: str) -> int:
    async with db.transaction() as session:
        result = await session.execute(
            text("INSERT INTO categories (name) VALUES (:n)"), {"n": name}
        )
        cat_id = result.lastrowid  # type: ignore[attr-defined]
        assert cat_id is not None
        return int(cat_id)


async def create_product(
    db: Database,
    *,
    category_id: int,
    name: str,
    description: str = "",
    price: int = 0,
    delivery_type: str = "text",
    delivery_payload: str = "",
    photo_file_id: str = "",
) -> int:
    async with db.transaction() as session:
        result = await session.execute(
            text(
                "INSERT INTO products (category_id, name, description, price, "
                "delivery_type, delivery_payload, photo_file_id) "
                "VALUES (:cid, :n, :d, :p, :dt, :dp, :pf)"
            ),
            {
                "cid": category_id,
                "n": name,
                "d": description,
                "p": price,
                "dt": delivery_type,
                "dp": delivery_payload,
                "pf": photo_file_id,
            },
        )
        prod_id = result.lastrowid  # type: ignore[attr-defined]
        assert prod_id is not None
        return int(prod_id)


async def get_order_stats(db: Database, period: str = "day") -> dict[str, int]:
    interval = "1 day" if period == "day" else "7 days"
    async with db.session() as session:
        result = await session.execute(
            text(
                f"SELECT status, COUNT(*) as cnt, SUM(amount) as total "
                f"FROM orders WHERE created_at >= datetime('now', '-{interval}') "
                f"GROUP BY status"
            )
        )
        rows = result.mappings().all()
        return {r["status"]: r["cnt"] for r in rows}



async def update_category(
    db: Database,
    category_id: int,
    *,
    name: str | None = None,
    position: int | None = None,
    is_active: bool | None = None,
) -> bool:
    """Partially update a category. Returns False when the category does not exist."""
    sets: list[str] = []
    params: dict[str, Any] = {"cid": category_id}
    if name is not None:
        sets.append("name = :n")
        params["n"] = name
    if position is not None:
        sets.append("position = :pos")
        params["pos"] = position
    if is_active is not None:
        sets.append("is_active = :ia")
        params["ia"] = 1 if is_active else 0
    if not sets:
        return False
    async with db.transaction() as session:
        result = await session.execute(
            text(
                "UPDATE categories SET " + ", ".join(sets) + " WHERE id = :cid"
            ),
            params,
        )
        return bool(result.rowcount)  # type: ignore[attr-defined]


async def delete_category(db: Database, category_id: int) -> bool:
    """Soft-delete a category (is_active = 0).

    Refuses when the category still has products (protects existing orders and
    carts from dangling references). Returns False on refusal or missing category.
    """
    async with db.transaction() as session:
        product_count = await session.execute(
            text("SELECT COUNT(*) FROM products WHERE category_id = :cid"),
            {"cid": category_id},
        )
        if int(product_count.scalar_one()) > 0:
            return False
        result = await session.execute(
            text("UPDATE categories SET is_active = 0 WHERE id = :cid"),
            {"cid": category_id},
        )
        return bool(result.rowcount)  # type: ignore[attr-defined]


async def toggle_category(db: Database, category_id: int) -> bool | None:
    """Invert category is_active. Returns the new value, or None when missing."""
    async with db.transaction() as session:
        row = await session.execute(
            text("SELECT is_active FROM categories WHERE id = :cid"),
            {"cid": category_id},
        )
        current = row.scalar_one_or_none()
        if current is None:
            return None
        new_value = 0 if current else 1
        await session.execute(
            text("UPDATE categories SET is_active = :ia WHERE id = :cid"),
            {"ia": new_value, "cid": category_id},
        )
        return bool(new_value)


async def get_categories_admin(db: Database) -> list[dict[str, Any]]:
    """All categories (including inactive) with product counts, for the admin UI."""
    async with db.session() as session:
        result = await session.execute(
            text(
                "SELECT c.id, c.name, c.position, c.is_active, "
                "COUNT(p.id) AS product_count "
                "FROM categories c "
                "LEFT JOIN products p ON p.category_id = c.id AND p.is_active = 1 "
                "GROUP BY c.id ORDER BY c.position"
            )
        )
        return [dict(r) for r in result.mappings().all()]


async def update_product(
    db: Database,
    product_id: int,
    *,
    category_id: int | None = None,
    name: str | None = None,
    description: str | None = None,
    price: int | None = None,
    delivery_type: str | None = None,
    delivery_payload: str | None = None,
    photo_file_id: str | None = None,
    is_active: bool | None = None,
) -> bool:
    """Partially update a product. Returns False when the product does not exist."""
    sets: list[str] = []
    params: dict[str, Any] = {"pid": product_id}
    if category_id is not None:
        sets.append("category_id = :cid")
        params["cid"] = category_id
    if name is not None:
        sets.append("name = :n")
        params["n"] = name
    if description is not None:
        sets.append("description = :d")
        params["d"] = description
    if price is not None:
        sets.append("price = :p")
        params["p"] = price
    if delivery_type is not None:
        sets.append("delivery_type = :dt")
        params["dt"] = delivery_type
    if delivery_payload is not None:
        sets.append("delivery_payload = :dp")
        params["dp"] = delivery_payload
    if photo_file_id is not None:
        sets.append("photo_file_id = :pf")
        params["pf"] = photo_file_id
    if is_active is not None:
        sets.append("is_active = :ia")
        params["ia"] = 1 if is_active else 0
    if not sets:
        return False
    async with db.transaction() as session:
        result = await session.execute(
            text("UPDATE products SET " + ", ".join(sets) + " WHERE id = :pid"),
            params,
        )
        return bool(result.rowcount)  # type: ignore[attr-defined]


async def delete_product(db: Database, product_id: int) -> bool:
    """Soft-delete a product (is_active = 0).

    Refuses when the product has unfulfilled orders
    (created / pending_payment / paid). Returns False on refusal or missing.
    """
    async with db.transaction() as session:
        order_count = await session.execute(
            text(
                "SELECT COUNT(*) FROM orders WHERE product_id = :pid "
                "AND status IN ('created', 'pending_payment', 'paid')"
            ),
            {"pid": product_id},
        )
        if int(order_count.scalar_one()) > 0:
            return False
        result = await session.execute(
            text("UPDATE products SET is_active = 0 WHERE id = :pid"),
            {"pid": product_id},
        )
        return bool(result.rowcount)  # type: ignore[attr-defined]


async def toggle_product(db: Database, product_id: int) -> bool | None:
    """Invert product is_active. Returns the new value, or None when missing."""
    async with db.transaction() as session:
        row = await session.execute(
            text("SELECT is_active FROM products WHERE id = :pid"),
            {"pid": product_id},
        )
        current = row.scalar_one_or_none()
        if current is None:
            return None
        new_value = 0 if current else 1
        await session.execute(
            text("UPDATE products SET is_active = :ia WHERE id = :pid"),
            {"ia": new_value, "pid": product_id},
        )
        return bool(new_value)


async def get_product_admin(db: Database, product_id: int) -> dict[str, Any] | None:
    """Fetch any product (including inactive) by id for the admin UI."""
    async with db.session() as session:
        result = await session.execute(
            text("SELECT * FROM products WHERE id = :id"), {"id": product_id}
        )
        row = result.mappings().fetchone()
        return dict(row) if row else None


async def add_keys(db: Database, product_id: int, values: list[str]) -> int:
    """Bulk-insert key stock for a product. Returns the number of rows inserted."""
    if not values:
        return 0
    async with db.transaction() as session:
        for value in values:
            await session.execute(
                text(
                    "INSERT INTO keys (product_id, value, used_by) "
                    "VALUES (:pid, :v, NULL)"
                ),
                {"pid": product_id, "v": value},
            )
        return len(values)


async def get_stock(db: Database, product_id: int) -> dict[str, int]:
    """Return total / used / available key counts for a product."""
    async with db.session() as session:
        total = await session.execute(
            text("SELECT COUNT(*) FROM keys WHERE product_id = :pid"),
            {"pid": product_id},
        )
        used = await session.execute(
            text(
                "SELECT COUNT(*) FROM keys WHERE product_id = :pid AND used_by IS NOT NULL"
            ),
            {"pid": product_id},
        )
        total_val = int(total.scalar_one())
        used_val = int(used.scalar_one())
        return {
            "total": total_val,
            "used": used_val,
            "available": total_val - used_val,
        }


async def manual_fulfill_order(db: Database, order_id: int, payload: str) -> bool:
    """Admin manually delivers an already-paid order.

    Idempotent: guarded UPDATE on status='paid', inserts delivery only once.
    Returns False when the order is missing or already fulfilled.
    """
    async with db.transaction() as session:
        result = await session.execute(
            text(
                "UPDATE orders SET status = 'delivered', delivered_at = datetime('now') "
                "WHERE id = :oid AND status = 'paid' RETURNING product_id"
            ),
            {"oid": order_id},
        )
        row = result.first()
        if row is None:
            return False
        int(row[0])
        existing = await session.execute(
            text("SELECT 1 FROM product_deliveries WHERE order_id = :oid LIMIT 1"),
            {"oid": order_id},
        )
        if existing.first() is not None:
            return True
        await session.execute(
            text(
                "INSERT INTO product_deliveries (order_id, payload) VALUES (:oid, :p)"
            ),
            {"oid": order_id, "p": payload},
        )
        return True


async def cancel_order(db: Database, order_id: int) -> bool:
    """Cancel an order that is not yet paid (created / pending_payment).

    Returns False when the order is missing or already beyond cancellable state.
    """
    async with db.transaction() as session:
        result = await session.execute(
            text(
                "UPDATE orders SET status = 'cancelled' "
                "WHERE id = :oid AND status IN ('created', 'pending_payment')"
            ),
            {"oid": order_id},
        )
        return bool(result.rowcount)  # type: ignore[attr-defined]


async def refund_order(
    db: Database, order_id: int, *, bot_token: str | None = None
) -> bool:
    """Mark a paid order as refunded and call Telegram refundStarPayment.

    The actual Telegram Stars refund is performed via the
    refundStarPayment Bot API method when bot_token is provided.
    The database record is updated idempotently afterwards.
    Returns False when the order is missing or not in a refundable state,
    or when the Telegram API call fails (if a token was provided).
    """
    async with db.transaction() as session:
        # Fetch order details needed for the Telegram API call.
        order_result = await session.execute(
            text("SELECT user_id, amount FROM orders WHERE id = :oid"),
            {"oid": order_id},
        )
        order_row = order_result.first()
        if order_row is None:
            return False
        user_id = int(order_row[0])
        amount = int(order_row[1])

        # Fetch the Stars payment charge id from the payments ledger.
        payment_result = await session.execute(
            text(
                "SELECT external_id FROM payments "
                "WHERE order_id = :oid AND provider = 'stars' AND status = 'succeeded'"
            ),
            {"oid": order_id},
        )
        payment_row = payment_result.first()
        charge_id = str(payment_row[0]) if payment_row else None

        # Call Telegram refundStarPayment API when a token is available.
        if bot_token and charge_id:
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.post(
                        f"https://api.telegram.org/bot{bot_token}/refundStarPayment",
                        json={
                            "user_id": user_id,
                            "payment_charge_id": charge_id,
                            "amount": amount,
                        },
                        timeout=10.0,
                    )
                    if not resp.is_success:
                        # API call failed - do not mark the order as refunded
                        # so the admin can retry.
                        return False
            except httpx.HTTPError:
                return False

        # Mark the order as refunded in the database (idempotent).
        result = await session.execute(
            text(
                "UPDATE orders SET status = 'refunded', delivered_at = datetime('now') "
                "WHERE id = :oid AND status IN ('paid', 'delivered')"
            ),
            {"oid": order_id},
        )
        return bool(result.rowcount)  # type: ignore[attr-defined]


async def get_orders_by_status(
    db: Database, status: str | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    """List orders, optionally filtered by status, most recent first."""
    async with db.session() as session:
        if status is None:
            result = await session.execute(
                text(
                    "SELECT o.*, p.name AS product_name FROM orders o "
                    "JOIN products p ON o.product_id = p.id "
                    "ORDER BY o.created_at DESC LIMIT :lim"
                ),
                {"lim": limit},
            )
        else:
            result = await session.execute(
                text(
                    "SELECT o.*, p.name AS product_name FROM orders o "
                    "JOIN products p ON o.product_id = p.id "
                    "WHERE o.status = :st ORDER BY o.created_at DESC LIMIT :lim"
                ),
                {"st": status, "lim": limit},
            )
        return [dict(r) for r in result.mappings().all()]


async def get_orders_for_user(
    db: Database, user_id: int, status: str | None = None
) -> list[dict[str, Any]]:
    """List a user's orders, optionally filtered by status."""
    async with db.session() as session:
        if status is None:
            result = await session.execute(
                text(
                    "SELECT o.*, p.name AS product_name FROM orders o "
                    "JOIN products p ON o.product_id = p.id "
                    "WHERE o.user_id = :uid ORDER BY o.created_at DESC"
                ),
                {"uid": user_id},
            )
        else:
            result = await session.execute(
                text(
                    "SELECT o.*, p.name AS product_name FROM orders o "
                    "JOIN products p ON o.product_id = p.id "
                    "WHERE o.user_id = :uid AND o.status = :st "
                    "ORDER BY o.created_at DESC"
                ),
                {"uid": user_id, "st": status},
            )
        return [dict(r) for r in result.mappings().all()]


async def get_sales_stats(
    db: Database, period: str = "day"
) -> dict[str, int]:
    """Aggregated sales: paid_count, delivered_count, revenue, refunded_count."""
    interval = "1 day" if period == "day" else "7 days"
    async with db.session() as session:
        result = await session.execute(
            text(
                f"SELECT status, COUNT(*) as cnt, SUM(amount) as total "
                f"FROM orders WHERE created_at >= datetime('now', '-{interval}') "
                f"GROUP BY status"
            )
        )
        rows = result.mappings().all()
    stats: dict[str, int] = {
        "paid_count": 0,
        "delivered_count": 0,
        "revenue": 0,
        "refunded_count": 0,
    }
    for r in rows:
        status = r["status"]
        cnt = int(r["cnt"])
        total = int(r["total"] or 0)
        if status == "paid":
            stats["paid_count"] = cnt
        elif status == "delivered":
            stats["delivered_count"] = cnt
            stats["revenue"] += total
        elif status == "refunded":
            stats["refunded_count"] = cnt
    return stats


async def get_low_stock_products(
    db: Database, threshold: int = 5
) -> list[dict[str, Any]]:
    """Products (text delivery with key pool) whose available keys <= threshold."""
    async with db.session() as session:
        result = await session.execute(
            text(
                "SELECT p.id, p.name, COUNT(k.id) AS total_keys, "
                "SUM(CASE WHEN k.used_by IS NULL THEN 1 ELSE 0 END) AS available_keys "
                "FROM products p "
                "LEFT JOIN keys k ON k.product_id = p.id "
                "WHERE p.delivery_type = 'text' AND p.is_active = 1 "
                "GROUP BY p.id "
                "HAVING available_keys <= :thr OR available_keys IS NULL "
                "ORDER BY available_keys ASC"
            ),
            {"thr": threshold},
        )
        return [dict(r) for r in result.mappings().all()]
