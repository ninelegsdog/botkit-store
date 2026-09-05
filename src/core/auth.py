from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from src.core.database import Database


class AdminGate:
    def __init__(self, password: str, admin_ids: list[int] | None = None) -> None:
        self._password = password
        self._admin_ids = set(admin_ids or [])
        self._authorized: set[int] = set()
        self._attempts: dict[int, list[float]] = {}
        self._throttle_window = 300.0
        self._max_attempts = 5

    def is_admin(self, user_id: int) -> bool:
        return user_id in self._admin_ids or user_id in self._authorized

    def authorize(self, user_id: int, password: str) -> bool:
        if password != self._password:
            now = time.time()
            attempts = self._attempts.setdefault(user_id, [])
            attempts[:] = [t for t in attempts if now - t < self._throttle_window]
            attempts.append(now)
            return False
        self._authorized.add(user_id)
        self._attempts.pop(user_id, None)
        return True

    def deauthorize(self, user_id: int) -> None:
        self._authorized.discard(user_id)

    def is_throttled(self, user_id: int) -> bool:
        now = time.time()
        attempts = self._attempts.get(user_id, [])
        attempts[:] = [t for t in attempts if now - t < self._throttle_window]
        return len(attempts) >= self._max_attempts


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

