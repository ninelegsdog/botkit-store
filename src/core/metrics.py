from __future__ import annotations

import logging
from typing import Any

from aiohttp import web
from botkit_core.metrics import (
    BOTKIT_ERRORS_TOTAL,
    BOTKIT_UPDATES_TOTAL,
)
from prometheus_client import CONTENT_TYPE_LATEST, Counter, generate_latest

try:
    from botkit_core import __version__ as _core_version
except ImportError:
    _core_version = "0.0.0"

logger = logging.getLogger(__name__)

UPDATES_TOTAL = BOTKIT_UPDATES_TOTAL
ERRORS_TOTAL = BOTKIT_ERRORS_TOTAL
ORDERS_TOTAL = Counter(
    "bot_orders_total",
    "Orders created",
)


class Metrics:
    """Legacy in-memory counters kept for webhook/health reporting.

    Also bumps prometheus counters so both views stay consistent.
    """

    def __init__(self) -> None:
        import time

        self._start: float = time.time()
        self.messages_processed: int = 0
        self.orders_created: int = 0
        self.orders_delivered: int = 0
        self.errors: int = 0

    def inc_messages(self) -> None:
        self.messages_processed += 1

    def inc_orders(self) -> None:
        self.orders_created += 1
        ORDERS_TOTAL.inc()

    def inc_delivered(self) -> None:
        self.orders_delivered += 1

    def inc_errors(self) -> None:
        self.errors += 1
        ERRORS_TOTAL.labels(error_type="domain").inc()

    def uptime_seconds(self) -> float:
        import time

        return time.time() - self._start


class UpdatesMiddleware:
    """Counts every incoming update."""

    async def __call__(
        self,
        handler: Any,
        event: Any,
        data: dict[str, Any],
    ) -> Any:
        UPDATES_TOTAL.labels(type=type(event).__name__.lower()).inc()
        return await handler(event, data)


async def health(request: web.Request) -> web.Response:
    accept = request.headers.get("Accept", "")
    if "application/json" in accept:
        return web.json_response({"status": "ok", "version": _core_version})
    return web.Response(text="ok")


async def version(request: web.Request) -> web.Response:
    return web.json_response({"version": _core_version, "service": "botkit"})


async def metrics(request: web.Request) -> web.Response:
    return web.Response(body=generate_latest(), headers={"Content-Type": CONTENT_TYPE_LATEST})


def create_metrics_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/health", health)
    app.router.add_get("/version", version)
    app.router.add_get("/metrics", metrics)
    return app


async def start_metrics_server(port: int) -> web.AppRunner:
    runner = web.AppRunner(create_metrics_app())
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info("Metrics server started on port %s", port)
    return runner
