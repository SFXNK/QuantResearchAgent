"""Sandbox boundary.

A sandbox runs the backtest entrypoint (`quant_research_agent.research.runner`) against
agent-written strategy code under isolation. Two properties matter:

- *Safety*: agent code cannot harm the host (resource limits, dropped caps,
  read-only rootfs, restricted syscalls).
- *Integrity*: networking is denied, which structurally prevents the agent from
  fetching future data or exfiltrating the holdout.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(slots=True)
class SandboxResult:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool
    duration_s: float

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out


class SandboxRunner(Protocol):
    backend: str
    network_disabled: bool

    def run_backtest(
        self,
        strategy_path: Path,
        events_path: Path,
        sim_config_path: Path,
        interval: int,
        out_path: Path,
    ) -> SandboxResult: ...
