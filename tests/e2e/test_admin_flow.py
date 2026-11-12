"""Real-Telegram E2E: admin flow — /admin requests a password, wrong password rejected.

Requires RUN_TELEGRAM_E2E=1 and Telethon secrets (see tests/e2e/conftest.py).
"""
from __future__ import annotations

import asyncio
import os

import pytest

pytest.importorskip("telethon")
from telethon import events  # noqa: E402

pytestmark = [
    pytest.mark.req,
    pytest.mark.e2e,
    pytest.mark.serial,
]


async def wait_for_bot_message(client, bot, *, predicate, trigger, wait_timeout):
    done = asyncio.Event()
    matched: dict = {}

    async def on_message(event):
        if predicate(event.message):
            matched["message"] = event.message
            done.set()

    client.add_event_handler(on_message, events.NewMessage(from_users=bot))
    try:
        await trigger()
        await asyncio.wait_for(done.wait(), timeout=wait_timeout)
        return matched["message"]
    finally:
        client.remove_event_handler(on_message)


@pytest.mark.asyncio
async def test_admin_asks_for_password(telegram_user_client) -> None:
    """Sending /admin to the bot should ask for the admin password."""
    client = telegram_user_client
    bot = await client.get_entity(os.environ["TEST_BOT_USERNAME"])
    wait_timeout = float(os.getenv("TELEGRAM_E2E_TIMEOUT", "20"))

    response = await wait_for_bot_message(
        client,
        bot,
        predicate=lambda message: "пароль" in (message.raw_text or "").lower(),
        trigger=lambda: client.send_message(bot, "/admin"),
        wait_timeout=wait_timeout,
    )
    assert "пароль" in (response.raw_text or "").lower()


@pytest.mark.asyncio
async def test_admin_rejects_wrong_password(telegram_user_client) -> None:
    """Sending a wrong password after /admin should be rejected."""
    client = telegram_user_client
    bot = await client.get_entity(os.environ["TEST_BOT_USERNAME"])
    wait_timeout = float(os.getenv("TELEGRAM_E2E_TIMEOUT", "20"))

    # Trigger /admin
    await client.send_message(bot, "/admin")
    await asyncio.sleep(0.5)

    # Send wrong password
    response = await wait_for_bot_message(
        client,
        bot,
        predicate=lambda message: "неверн" in (message.raw_text or "").lower()
        or "ошибк" in (message.raw_text or "").lower(),
        trigger=lambda: client.send_message(bot, "wrong_password_12345"),
        wait_timeout=wait_timeout,
    )
    text = (response.raw_text or "").lower()
    assert "неверн" in text or "ошибк" in text
