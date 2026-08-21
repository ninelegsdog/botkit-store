from __future__ import annotations

import pytest

from src.core.config import Config
from src.core.ui import escape, order_card, product_card


@pytest.mark.asyncio
async def test_config_from_env(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "test_token")
    config = Config.from_env()
    assert config.bot_token == "test_token"


def test_escape():
    assert escape("<script>") == "&lt;script&gt;"
    assert escape("hello") == "hello"
    assert escape(None) == ""


def test_product_card():
    card = product_card({
        "name": "Test <script>",
        "price": 100,
        "description": "A test product",
    })
    assert "<script>" not in card
    assert "Test" in card


def test_order_card():
    card = order_card({
        "id": 1,
        "status": "paid",
        "amount": 100,
    })
    assert "paid" in card
    assert "100" in card
