from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

logger = logging.getLogger(__name__)


class ThrottlingMiddleware(BaseMiddleware):
    # Сколько секунд между извинениями одному пользователю: шторм из десяти
    # сообщений не должен порождать поток извинений (F3).
    APOLOGY_INTERVAL = 5.0

    def __init__(
        self,
        min_interval: float = 2.0,
        redis_url: str = "",
        apology_text: str = "",
    ) -> None:
        super().__init__()
        self._min_interval = min_interval
        self._redis_url = redis_url
        self._apology_text = apology_text
        self._last_message: dict[int, float] = {}
        self._last_apology: dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Message):
            user_id = event.from_user.id if event.from_user else 0
            now = time.time()
            last = self._last_message.get(user_id, 0.0)
            if now - last < self._min_interval:
                # F3: раньше здесь был молчаливый return None — сообщение
                # исчезало без ответа и без записи в лог, со стороны
                # пользователя «бот игнорирует», а при разборе флаки это
                # выглядело как дефект бота. Теперь: причина дропа в логе,
                # а на дроп — вежливое извинение (не чаще APOLOGY_INTERVAL,
                # чтобы шторм не порождал поток извинений).
                since_apology = now - self._last_apology.get(user_id, 0.0)
                send_apology = bool(self._apology_text) and since_apology >= self.APOLOGY_INTERVAL
                logger.info(
                    "throttled: user %s прислал сообщение через %.2f с (< %.2f с) — дроп; извинение=%s",
                    user_id,
                    now - last,
                    self._min_interval,
                    send_apology,
                )
                if send_apology:
                    self._last_apology[user_id] = now
                    await event.answer(self._apology_text)
                return None
            self._last_message[user_id] = now
        return await handler(event, data)
