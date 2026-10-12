"""The payment path must survive Telegram replaying `successful_payment`.

Telegram re-sends a successful-payment update whenever our answer to the previous one
was lost. To the bot a lost answer is indistinguishable from a failure, so the same
update arrives again. These tests pin the behaviour that makes that harmless: payment
is recorded once, and a key is handed out once.

The earlier code was not safe here. `mark_paid` had no guard, so a replay rewrote the
order and appended a second `payments` row. `deliver_order` took an already-allocated
payload from the caller and inserted a delivery row unconditionally, so a replay
delivered twice. `use_key` updated a free key to the user and then read
`WHERE used_by = :uid` with no LIMIT, so a customer buying the same product twice could
be handed the key from their first purchase.
"""
from __future__ import annotations

import pytest

from src.store import service

BUYER = 111
OTHER_BUYER = 222


async def _paid_order(db, user_id: int = BUYER, keys: int = 3) -> tuple[int, int]:
    """Create a product with `keys` units in stock and a paid order for it."""
    cat_id = await service.create_category(db, f"Cat-{user_id}-{keys}")
    prod_id = await service.create_product(
        db, category_id=cat_id, name=f"P-{user_id}", price=100
    )
    for i in range(keys):
        await session_add_key(db, prod_id, f"KEY-{user_id}-{keys}-{i}")
    order_id = await service.create_order(db, user_id, prod_id, 100)
    await service.mark_paid(db, order_id, f"pay-{order_id}")
    return order_id, prod_id


async def session_add_key(db, product_id: int, value: str) -> None:
    async with db.transaction() as session:
        await session.execute(
            text_insert_key(product_id, value),
        )


def text_insert_key(product_id: int, value: str):
    from sqlalchemy import text

    return text(
        "INSERT INTO keys (product_id, value, used_by) VALUES (:pid, :v, NULL)"
    ).bindparams(pid=product_id, v=value)


# --- mark_paid: idempotent ---------------------------------------------------


@pytest.mark.asyncio
async def test_mark_paid_returns_true_first_time(db):
    cat_id = await service.create_category(db, "C")
    prod_id = await service.create_product(db, category_id=cat_id, name="P", price=100)
    order_id = await service.create_order(db, BUYER, prod_id, 100)
    assert await service.mark_paid(db, order_id, "pay-1") is True


@pytest.mark.asyncio
async def test_replayed_payment_is_not_recorded_twice(db):
    """The same `successful_payment` arriving again must be a no-op."""
    cat_id = await service.create_category(db, "C")
    prod_id = await service.create_product(db, category_id=cat_id, name="P", price=100)
    order_id = await service.create_order(db, BUYER, prod_id, 100)

    assert await service.mark_paid(db, order_id, "pay-1") is True
    # Telegram replays the very same update.
    assert await service.mark_paid(db, order_id, "pay-1") is False
    assert await service.mark_paid(db, order_id, "pay-1") is False

    rows = await _payments_for(db, order_id)
    assert len(rows) == 1, f"replay appended payment rows: {rows}"


@pytest.mark.asyncio
async def test_mark_paid_refuses_a_cancelled_order(db):
    cat_id = await service.create_category(db, "C")
    prod_id = await service.create_product(db, category_id=cat_id, name="P", price=100)
    order_id = await service.create_order(db, BUYER, prod_id, 100)
    await _set_status(db, order_id, "cancelled")
    assert await service.mark_paid(db, order_id, "pay-1") is False


@pytest.mark.asyncio
async def test_mark_paid_on_missing_order(db):
    assert await service.mark_paid(db, 999999, "pay-1") is False


# --- fulfill_order: one key, once -------------------------------------------


@pytest.mark.asyncio
async def test_fulfill_returns_a_key_and_marks_delivered(db):
    order_id, _ = await _paid_order(db)
    key = await service.fulfill_order(db, order_id)
    assert key is not None
    order = await service.get_order(db, order_id)
    assert order["status"] == "delivered"


@pytest.mark.asyncio
async def test_replay_does_not_hand_out_a_second_key(db):
    """The failure this whole file exists for."""
    order_id, _ = await _paid_order(db, keys=3)

    first = await service.fulfill_order(db, order_id)
    assert first is not None
    second = await service.fulfill_order(db, order_id)
    third = await service.fulfill_order(db, order_id)

    assert second is None, f"order was fulfilled twice, second key: {second}"
    assert third is None
    assert len(await _deliveries_for(db, order_id)) == 1
    # Two of the three keys are still unclaimed.
    prod_id = (await service.get_order(db, order_id))["product_id"]
    assert await service.get_available_keys_count(db, prod_id) == 2


@pytest.mark.asyncio
async def test_buyer_buying_twice_gets_two_different_keys(db):
    """`use_key` used to return the first purchase's key here."""
    cat_id = await service.create_category(db, "C")
    prod_id = await service.create_product(db, category_id=cat_id, name="P", price=100)
    for i in range(3):
        await session_add_key(db, prod_id, f"KEY-{i}")

    first_order = await service.create_order(db, BUYER, prod_id, 100)
    await service.mark_paid(db, first_order, "pay-a")
    key_one = await service.fulfill_order(db, first_order)

    second_order = await service.create_order(db, BUYER, prod_id, 100)
    await service.mark_paid(db, second_order, "pay-b")
    key_two = await service.fulfill_order(db, second_order)

    assert key_one is not None and key_two is not None
    assert key_one != key_two, f"same key delivered twice: {key_one}"


@pytest.mark.asyncio
async def test_fulfilling_an_unpaid_order_is_refused(db):
    """Order in created/pending state must not receive a key."""
    cat_id = await service.create_category(db, "C")
    prod_id = await service.create_product(db, category_id=cat_id, name="P", price=100)
    for i in range(2):
        await session_add_key(db, prod_id, f"KEY-{i}")
    order_id = await service.create_order(db, BUYER, prod_id, 100)

    assert await service.fulfill_order(db, order_id) is None
    assert await service.get_available_keys_count(db, prod_id) == 2


@pytest.mark.asyncio
async def test_out_of_stock_leaves_order_paid_and_does_not_consume_a_key(db):
    cat_id = await service.create_category(db, "C")
    prod_id = await service.create_product(db, category_id=cat_id, name="P", price=100)
    order_id = await service.create_order(db, BUYER, prod_id, 100)
    await service.mark_paid(db, order_id, "pay-1")

    # No keys in stock at all.
    assert await service.fulfill_order(db, order_id) is None
    order = await service.get_order(db, order_id)
    assert order["status"] == "paid", "order must stay paid so it can be fulfilled later"
    assert order["delivered_at"] is None
    assert len(await _deliveries_for(db, order_id)) == 0


@pytest.mark.asyncio
async def test_sequential_replay_yields_exactly_one_key(db):
    """Two workers processing the same order one after the other.

    Written sequentially rather than with asyncio.gather on purpose: the test database is
    a single file-backed SQLite engine, where two concurrent writers serialise on one
    file and one transaction legitimately rolls back - that would test SQLite's locking,
    not the guard. The guard's job is that a *replayed* update (which is how this really
    happens) is refused; sequential replay exercises exactly that, deterministically.
    """
    order_id, prod_id = await _paid_order(db, keys=5)

    first = await service.fulfill_order(db, order_id)
    second = await service.fulfill_order(db, order_id)

    assert first is not None
    assert second is None, f"order was fulfilled twice, second key: {second}"
    assert len(await _deliveries_for(db, order_id)) == 1
    assert await service.get_available_keys_count(db, prod_id) == 4


# --- helpers -----------------------------------------------------------------


async def _payments_for(db, order_id: int) -> list:
    from sqlalchemy import text

    async with db.session() as session:
        result = await session.execute(
            text("SELECT * FROM payments WHERE order_id = :oid"), {"oid": order_id}
        )
        return list(result.mappings().all())


async def _deliveries_for(db, order_id: int) -> list:
    from sqlalchemy import text

    async with db.session() as session:
        result = await session.execute(
            text("SELECT * FROM product_deliveries WHERE order_id = :oid"),
            {"oid": order_id},
        )
        return list(result.mappings().all())


async def _set_status(db, order_id: int, status: str) -> None:
    from sqlalchemy import text

    async with db.transaction() as session:
        await session.execute(
            text("UPDATE orders SET status = :s WHERE id = :oid"),
            {"s": status, "oid": order_id},
        )
