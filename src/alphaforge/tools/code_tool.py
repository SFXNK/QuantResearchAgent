"""Strategy code editor tools."""

from __future__ import annotations

import ast

from pydantic import BaseModel, Field

from .base import Tool, ToolContext, ToolResult


class WriteStrategyArgs(BaseModel):
    filename: str = Field(description="Filename for the strategy module, e.g. 'momentum.py'.")
    code: str = Field(description="Full Python source. Must define build() -> Strategy.")


class WriteStrategyTool(Tool[WriteStrategyArgs]):
    name = "write_strategy"
    description = (
        "Write a strategy module to the workspace. The module MUST define a top-level "
        "function build() that returns an object with an on_observation(obs) -> list[Action] "
        "method. Use alphaforge.sim.base.Action / Observation and alphaforge.types.Side."
    )
    args_model = WriteStrategyArgs

    async def run(self, args: WriteStrategyArgs, ctx: ToolContext) -> ToolResult:
        if not args.filename.endswith(".py"):
            return ToolResult.error("filename must end with .py")
        # Reject obviously unsafe constructs early (defense in depth; the sandbox is the real guard).
        try:
            tree = ast.parse(args.code)
        except SyntaxError as exc:
            return ToolResult.error(f"syntax error: {exc}")
        if not any(
            isinstance(n, ast.FunctionDef) and n.name == "build" for n in ast.walk(tree)
        ):
            return ToolResult.error("code must define a top-level build() function")

        path = ctx.workspace / args.filename
        path.write_text(args.code)
        ctx.strategy_path = path
        return ToolResult(
            ok=True,
            content=f"Wrote {args.filename} ({len(args.code)} bytes). Ready to backtest.",
            data={"path": str(path)},
        )


class ReadStrategyArgs(BaseModel):
    filename: str


class ReadStrategyTool(Tool[ReadStrategyArgs]):
    name = "read_strategy"
    description = "Read back a previously written strategy module."
    args_model = ReadStrategyArgs

    async def run(self, args: ReadStrategyArgs, ctx: ToolContext) -> ToolResult:
        path = ctx.workspace / args.filename
        if not path.exists():
            return ToolResult.error(f"{args.filename} not found")
        return ToolResult(ok=True, content=path.read_text())
