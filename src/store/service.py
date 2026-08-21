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


async def mark_paid(db: Database, order_id: int, payment_id: str) -> None:
    async with db.transaction() as session:
        await session.execute(
            text(
                "UPDATE orders SET status = 'paid', payment_id = :pid WHERE id = :oid"
            ),
            {"pid": payment_id, "oid": order_id},
        )
        await session.execute(
            text(
                "INSERT INTO payments (order_id, provider, amount, status, external_id) "
                "VALUES (:oid, 'stars', (SELECT amount FROM orders WHERE id = :oid), 'succeeded', :eid)"
            ),
            {"oid": order_id, "eid": payment_id},
        )


async def deliver_order(db: Database, order_id: int, payload: str) -> None:
    async with db.transaction() as session:
        await session.execute(
            text(
                "UPDATE orders SET status = 'delivered', delivered_at = datetime('now') "
                "WHERE id = :oid"
            ),
            {"oid": order_id},
        )
        await session.execute(
            text(
                "INSERT INTO product_deliveries (order_id, payload) VALUES (:oid, :p)"
            ),
            {"oid": order_id, "p": payload},
        )


async def get_delivery(db: Database, order_id: int) -> dict[str, Any] | None:
    async with db.session() as session:
        result = await session.execute(
            text(
                "SELECT * FROM product_deliveries WHERE order_id = :oid LIMIT 1"
            ),
            {"oid": order_id},
        )
        row = result.mappings().fetchone()
        return dict(row) if row else None


async def use_key(db: Database, product_id: int, user_id: int) -> str | None:
    async with db.transaction() as session:
        result = await session.execute(
            text(
                "UPDATE keys SET used_by = :uid, used_at = datetime('now') "
                "WHERE product_id = :pid AND used_by IS NULL LIMIT 1"
            ),
            {"pid": product_id, "uid": user_id},
        )
        if result.rowcount == 0:  # type: ignore[attr-defined]
            return None
        key_result = await session.execute(
            text(
                "SELECT value FROM keys WHERE product_id = :pid AND used_by = :uid"
            ),
            {"pid": product_id, "uid": user_id},
        )
        row = key_result.fetchone()
        return str(row[0]) if row else None


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
