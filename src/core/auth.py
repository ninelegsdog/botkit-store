from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

# The gate lives in botkit-core and is re-exported rather than vendored. Five private
# copies meant five places for a security fix to land in only some of them; reminder's
# copy had already drifted into a different design. A re-export (not a subclass) keeps
# them from diverging again.
from botkit_core.admin import AdminGate as AdminGate

from src.core.database import Database


class AuthMiddleware(BaseMiddleware):
    def __init__(self, db: Database) -> None:
        super().__init__()
        self._db = db

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data["db"] = self._db
        return await handler(event, data)

