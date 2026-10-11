"""Callback parsing — validated integer argument of a Telegram callback payload.

Callback data is client-controlled (Telegram only enforces a 64-byte cap), so anything
a handler parses out of it is untrusted input. The fleet had `int(callback.data.split(":")[1])`
in six bots, which raises `ValueError` on malformed data and, in `botkit-store`, was the
first half of an IDOR: the parsed `order_id` was then used to read another user's data.

A shared implementation lives in `botkit_core.callbacks`. It is not imported here
because `botkit-core` is pinned by tag (`@v0.8.2`) and does not yet carry that module;
switching to the shim is a one-line import change when bots move to a core version that
ships it. Kept here so the store's authorisation fix is not blocked on a release.
"""
from __future__ import annotations

MAX_CALLBACK_BYTES = 64


def parse_callback_int(data: str | None, prefix: str) -> int | None:
    """Return the integer argument of `"<prefix><n>"`, or None if it is not exactly that.

    Returns None rather than raising so a handler can answer normally instead of pushing
    a `ValueError` into the error middleware. Rejects extra segments, whitespace, signs
    and over-long digit runs - `int()` alone would accept `"-1"`, `" 5"`, `"5:9"` and
    `"1_0"`.
    """
    if not data or not data.startswith(prefix):
        return None
    raw = data[len(prefix) :]
    if not raw or len(raw) > 18:  # more than 18 digits cannot be a rowid
        return None
    if not raw.isascii() or not raw.isdigit():
        return None
    return int(raw)


def callback_is_wellformed(data: str | None, prefix: str) -> bool:
    """True when `data` is a well-formed `"<prefix><n>"` within the 64-byte cap."""
    if data is not None and len(data.encode()) > MAX_CALLBACK_BYTES:
        return False
    return parse_callback_int(data, prefix) is not None
