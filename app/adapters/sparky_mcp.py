"""Bounded native SparkyFitness MCP transport. No model or generic tool executor."""
import asyncio
import json
import os
from contextvars import ContextVar
from pathlib import Path

import httpx


READ_TOOLS = frozenset({
    "sparky_search_foods", "sparky_get_food_details", "sparky_get_food_diary",
    "sparky_get_nutrition_summary", "sparky_get_goal_snapshot",
})
WRITE_ACTIONS = frozenset({"log_food", "update_entry", "delete_entry", "log_water"})
PROTOCOL = "2025-11-25"
request_tools = ContextVar('nutrition_request_tools', default=None)


class NutritionUnavailable(RuntimeError):
    pass


class SparkyMCP:
    def __init__(self):
        self.url = os.getenv("SPARKY_MCP_URL", "http://192.168.0.26:3004/mcp")
        self.ready = False
        self.lock = asyncio.Lock()

    async def rpc(self, method, params, write=False):
        filename = os.getenv("SPARKY_WRITE_TOKEN_FILE" if write else "SPARKY_READ_TOKEN_FILE", "")
        if not filename:
            raise NutritionUnavailable("Nutrition credential is not configured")
        try:
            token = Path(filename).read_text().strip()
            if not token:
                raise ValueError("empty credential")
            async with httpx.AsyncClient(timeout=httpx.Timeout(12, connect=3), follow_redirects=False, trust_env=False) as client:
                response = await client.post(self.url, headers={
                    "Authorization": "Bearer " + token,
                    "Accept": "application/json, text/event-stream",
                    "MCP-Protocol-Version": PROTOCOL,
                }, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
            response.raise_for_status()
            if len(response.content) > 1_000_000:
                raise ValueError("oversized result")
            body = response.json()
            if not isinstance(body, dict):
                raise ValueError('invalid JSON-RPC object')
            if body.get("id") != 1 or body.get("jsonrpc") != "2.0" or body.get("error"):
                raise ValueError("invalid JSON-RPC response")
            result = body["result"]
            if not isinstance(result, dict):
                raise ValueError('invalid MCP result')
            if result.get("isError"):
                raise ValueError("remote tool failed")
            return result
        except (OSError, ValueError, KeyError, TypeError, httpx.HTTPError) as error:
            # Never expose HTTP headers, remote health data or credential values.
            raise NutritionUnavailable("Nutrition request failed; no write will be automatically retried") from error

    async def call(self, name, arguments, write=False):
        if write:
            if name != "sparky_manage_food" or arguments.get("action") not in WRITE_ACTIONS:
                raise NutritionUnavailable("Nutrition write is outside the allowlist")
        elif name not in READ_TOOLS:
            raise NutritionUnavailable("Nutrition read is outside the allowlist")
        tools=request_tools.get()
        if tools is not None:
            tools.append(name)
        async with self.lock:
            if not self.ready:
                init = await self.rpc("initialize", {"protocolVersion": PROTOCOL, "capabilities": {}, "clientInfo": {"name": "jarvis-nutrition", "version": "1"}})
                if init.get("protocolVersion") != PROTOCOL or init.get("serverInfo", {}).get("name") != "sparkyfitness-mcp-server":
                    raise NutritionUnavailable("Unexpected nutrition MCP server")
                self.ready = True
        result = await self.rpc("tools/call", {"name": name, "arguments": arguments}, write)
        if "structuredContent" in result:
            value = result["structuredContent"]
        else:
            texts = [item.get("text", "") for item in result.get("content", []) if item.get("type") == "text"]
            if len(texts) != 1:
                raise NutritionUnavailable("Unsupported nutrition response")
            text = texts[0]
            if text.startswith("Error") or text.startswith("❌"):
                raise NutritionUnavailable("Nutrition operation was refused")
            try:
                value = json.loads(text)
            except ValueError:
                value = {"message": text}
        if isinstance(value, dict) and (value.get("error") or value.get("status") == "error"):
            raise NutritionUnavailable("Nutrition operation was refused")
        return value


sparky = SparkyMCP()
