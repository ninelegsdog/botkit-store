"""A customer must never read another customer's delivered payload.

`product_deliveries.payload` is the thing the store actually sells - a licence key, an
activation string. `get_delivery` is reached from a `store_redeliver:<order_id>`
callback, and callback data is fully client-controlled with sequential ids, so the
owner check cannot live only in the handler.
"""
from __future__ import annotations

import pytest

from src.store import service

OWNER = 111
INTRUDER = 999


async def _delivered_order(db, user_id: int, payload: str) -> int:
    cat_id = await service.create_category(db, f"Cat-{user_id}")
    prod_id = await service.create_product(
        db, category_id=cat_id, name=f"P-{user_id}", price=100
    )
    order_id = await service.create_order(db, user_id, prod_id, 100)
    await service.mark_paid(db, order_id, f"pay-{user_id}")
    await service.deliver_order(db, order_id, payload)
    return order_id


@pytest.mark.asyncio
async def test_owner_reads_their_own_delivery(db):
    order_id = await _delivered_order(db, OWNER, "OWNER-SECRET-KEY")
    delivery = await service.get_delivery(db, order_id, OWNER)
    assert delivery is not None
    assert delivery["payload"] == "OWNER-SECRET-KEY"


@pytest.mark.asyncio
async def test_another_user_cannot_read_it(db):
    """The regression this file exists for.

    Before the fix `get_delivery(db, order_id)` took no user and returned the payload
    to anyone who asked, so `store_redeliver:<id>` over ids 1..N disclosed every
    customer's goods.
    """
    order_id = await _delivered_order(db, OWNER, "OWNER-SECRET-KEY")
    assert await service.get_delivery(db, order_id, INTRUDER) is None


@pytest.mark.asyncio
async def test_enumeration_finds_nothing(db):
    """Sweep the id space the way an attacker would; every id must return None."""
    for uid in range(1, 8):
        await _delivered_order(db, uid, f"SECRET-{uid}")
    leaked = []
    for order_id in range(1, 12):
        for uid in (OWNER, INTRUDER):
            got = await service.get_delivery(db, order_id, uid)
            if got is not None:
                leaked.append((order_id, uid, got["payload"]))
    # Only the order that belongs to the asked-for user may come back.
    for order_id, uid, payload in leaked:
        assert uid == order_id, f"order {order_id} disclosed to user {uid}: {payload}"


@pytest.mark.asyncio
async def test_missing_order_is_not_an_error(db):
    assert await service.get_delivery(db, 999999, OWNER) is None
