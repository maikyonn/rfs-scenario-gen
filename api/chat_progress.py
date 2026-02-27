"""Thin shared module for pushing live progress events from sync @tool threads
to the async SSE stream.

Usage inside a sync @tool:
    from api.chat_progress import emit_tool_progress
    emit_tool_progress("validate_collision", "Launching esmini headless simulation…")

contextvars values set in the async context are inherited by executor threads
(Python docs: "When a new thread is created with concurrent.futures, a copy
of the context is used"), so the queue/loop tokens set in stream_chat are
visible inside the sync tool functions.
"""
from __future__ import annotations

import asyncio
import contextvars

_progress_queue: contextvars.ContextVar[asyncio.Queue | None] = contextvars.ContextVar(
    "_pq", default=None
)
_event_loop_var: contextvars.ContextVar[asyncio.AbstractEventLoop | None] = contextvars.ContextVar(
    "_el", default=None
)


def emit_tool_progress(tool_name: str, message: str) -> None:
    """Call from within a sync @tool to push a live progress update to the SSE stream.

    Uses loop.call_soon_threadsafe to safely cross the thread→asyncio boundary.
    Silently does nothing if no stream is active (e.g. during tests).
    """
    q = _progress_queue.get()
    loop = _event_loop_var.get()
    if q is not None and loop is not None and loop.is_running():
        loop.call_soon_threadsafe(q.put_nowait, {"tool": tool_name, "message": message})
