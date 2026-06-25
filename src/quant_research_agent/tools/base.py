"""Tool base types and the shared experiment context.

A `Tool` declares a Pydantic args model (so its JSON schema is generated, not
hand-written) and an async `run`. The `ToolContext` carries the per-experiment
state tools read and write (workspace, dataset, sandbox, last backtest, etc.).
"""

from __future__ import annotations

import abc
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from quant_research_agent.config import EvalConfig, SimConfig
from quant_research_agent.data.dataset import Dataset


@dataclass(slots=True)
class ToolResult:
    ok: bool
    content: str
    data: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def error(msg: str) -> ToolResult:
        return ToolResult(ok=False, content=f"ERROR: {msg}")


@dataclass
class ToolContext:
    workspace: Path
    dataset: Dataset
    sim_config: SimConfig
    eval_config: EvalConfig
    decision_interval_ns: int
    sandbox: Any | None = None  # SandboxRunner | None (avoid import cycle)
    # mutable per-experiment state
    strategy_path: Path | None = None
    last_backtest: dict[str, Any] | None = None
    submitted: bool = False
    submitted_strategy_path: Path | None = None
    hypotheses: list[str] = field(default_factory=list)


class Tool[ArgsT: BaseModel](abc.ABC):
    name: str
    description: str
    args_model: type[ArgsT]

    def json_schema(self) -> dict[str, Any]:
        """OpenAI-style function schema generated from the Pydantic args model."""
        schema = self.args_model.model_json_schema()
        schema.pop("title", None)
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": schema,
            },
        }

    def parse_args(self, raw: Mapping[str, Any]) -> ArgsT:
        return self.args_model.model_validate(dict(raw))

    @abc.abstractmethod
    async def run(self, args: ArgsT, ctx: ToolContext) -> ToolResult: ...
