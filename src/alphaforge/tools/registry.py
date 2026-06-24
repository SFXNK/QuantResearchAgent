"""Tool registry: schema export, validation, dispatch, and result truncation."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from alphaforge.models.base import ToolCall

from .base import Tool, ToolContext, ToolResult

_MAX_RESULT_CHARS = 6_000


class ToolRegistry:
    def __init__(self, tools: list[Tool] | None = None) -> None:
        self._tools: dict[str, Tool] = {}
        for t in tools or []:
            self.register(t)

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"duplicate tool {tool.name!r}")
        self._tools[tool.name] = tool

    def names(self) -> list[str]:
        return list(self._tools)

    def openai_schema(self) -> list[dict[str, Any]]:
        return [t.json_schema() for t in self._tools.values()]

    async def dispatch(self, call: ToolCall, ctx: ToolContext) -> ToolResult:
        tool = self._tools.get(call.name)
        if tool is None:
            return ToolResult.error(f"unknown tool {call.name!r}")
        try:
            args = tool.parse_args(call.arguments)
        except ValidationError as exc:
            return ToolResult.error(f"invalid arguments for {call.name}: {exc.errors()}")
        try:
            result = await tool.run(args, ctx)
        except Exception as exc:  # noqa: BLE001 - tools must never crash the loop
            return ToolResult.error(f"{type(exc).__name__}: {exc}")
        return self._truncate(result)

    @staticmethod
    def _truncate(result: ToolResult) -> ToolResult:
        if len(result.content) > _MAX_RESULT_CHARS:
            head = result.content[: _MAX_RESULT_CHARS - 200]
            result.content = (
                f"{head}\n... [truncated {len(result.content) - _MAX_RESULT_CHARS + 200} chars]"
            )
        return result
