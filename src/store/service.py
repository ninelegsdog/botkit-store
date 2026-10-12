from __future__ import annotations

from typing import Any

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
) -> int:
    async with db.transaction() as session:
        result = await session.execute(
            text(
                "INSERT INTO products (category_id, name, description, price, delivery_type, delivery_payload) "
                "VALUES (:cid, :n, :d, :p, :dt, :dp)"
            ),
            {
                "cid": category_id,
                "n": name,
                "d": description,
                "p": price,
                "dt": delivery_type,
                "dp": delivery_payload,
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
