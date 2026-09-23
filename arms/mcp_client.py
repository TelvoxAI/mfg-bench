"""A synchronous MCP client for the client-side tool loop of the arms (IND-982 Part I).

When Claude runs on Bedrock there is no server-side MCP connector, so the harness owns
the loop: it lists the server's tools, hands them to the model as ordinary tools, calls
the MCP server for every `tool_use` and returns the result — timing each call. That is
also what makes the latency numbers honest: per tool call, per model turn, per question.

The MCP Python SDK is async; this wrapper runs one event loop in a background thread and
keeps a session open per server so every call does not pay a fresh handshake.
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from typing import Any


class McpToolClient:
    def __init__(self, url: str, token: str = "", timeout: float = 120.0):
        self.url, self.token, self.timeout = url, token, timeout
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()
        self._session = None
        self._stack = None
        self._tools: list[dict] | None = None
        self._run(self._connect())

    def _run(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout=self.timeout + 30)

    async def _connect(self) -> None:
        from contextlib import AsyncExitStack

        import httpx
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client

        self._stack = AsyncExitStack()
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        http = await self._stack.enter_async_context(httpx.AsyncClient(headers=headers, timeout=self.timeout))
        r, w, *_ = await self._stack.enter_async_context(streamable_http_client(self.url, http_client=http))
        self._session = await self._stack.enter_async_context(ClientSession(r, w))
        await self._session.initialize()

    def tools(self) -> list[dict]:
        """Tools in the Anthropic `tools` shape (name, description, input_schema)."""
        if self._tools is None:
            res = self._run(self._session.list_tools())
            self._tools = [{"name": t.name, "description": t.description or "",
                            "input_schema": (getattr(t, "input_schema", None) or getattr(t, "inputSchema", None) or {"type": "object", "properties": {}})}
                           for t in res.tools]
        return self._tools

    def call(self, name: str, args: dict[str, Any]) -> tuple[str, bool, float]:
        """(result text, is_error, seconds).

        A streamable-HTTP session does not live forever: the server (Cloud Run behind the
        Indax MCP) closes it after a while, and every later call on it fails with
        `McpError: Connection closed`. Found on 2026-09-23: from the 30th question of a
        run onward every Indax tool call failed, and the model answered "connection
        error" 74 times. A real client reconnects; so does this one — once per call, and
        the reconnect is counted so the latency log can show it."""
        t0 = time.time()
        try:
            res = self._run(self._session.call_tool(name, args))
        except Exception as e:  # the tool loop must survive a broken tool call
            if not self._reconnect():
                return f"tool error: {type(e).__name__}: {e}", True, time.time() - t0
            try:
                res = self._run(self._session.call_tool(name, args))
            except Exception as e2:
                return f"tool error: {type(e2).__name__}: {e2}", True, time.time() - t0
        dt = time.time() - t0
        sc = getattr(res, "structured_content", None)
        if sc:
            text = json.dumps(sc.get("result", sc) if isinstance(sc, dict) else sc, ensure_ascii=False)
        else:
            text = "\n".join(getattr(c, "text", "") for c in (res.content or []) if getattr(c, "text", ""))
        return text, bool(getattr(res, "is_error", False)), dt

    def _reconnect(self) -> bool:
        """Drop the dead session and open a fresh one on the same loop."""
        self.reconnects = getattr(self, "reconnects", 0) + 1
        try:
            # The dead stack is abandoned, not closed: its contexts were entered in the
            # connect task, and anyio refuses to exit a cancel scope from another task.
            self._stack, self._session = None, None
            self._run(self._connect())
            return True
        except Exception:
            return False

    def close(self) -> None:
        if self._stack is not None:
            try:
                self._run(self._stack.aclose())
            except Exception:
                pass
        self._loop.call_soon_threadsafe(self._loop.stop)
