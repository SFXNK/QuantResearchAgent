"""Research-journal memory.

Carries compact summaries of *prior* experiments into the next one so the agent
can avoid repeating dead ends and can build on what generalized. The journal is
owned by the orchestrator and updated with holdout outcomes after each
experiment; a rendered summary is injected into the next experiment's prompt.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class JournalEntry:
    experiment_id: int
    hypothesis: str
    strategy_name: str
    val_sharpe: float
    holdout_sharpe: float | None = None
    survived: bool | None = None


@dataclass
class Journal:
    entries: list[JournalEntry] = field(default_factory=list)
    max_entries: int = 50

    def add(self, entry: JournalEntry) -> None:
        self.entries.append(entry)
        if len(self.entries) > self.max_entries:
            self.entries = self.entries[-self.max_entries :]

    def render(self, limit: int = 10) -> str:
        if not self.entries:
            return "(no prior experiments)"
        lines = []
        for e in self.entries[-limit:]:
            verdict = (
                "survived OOS"
                if e.survived
                else "failed OOS"
                if e.survived is False
                else "pending"
            )
            ho = "n/a" if e.holdout_sharpe is None else f"{e.holdout_sharpe:.2f}"
            lines.append(
                f"- exp {e.experiment_id}: {e.strategy_name} | val_sharpe={e.val_sharpe:.2f} "
                f"holdout_sharpe={ho} -> {verdict}. Idea: {e.hypothesis[:120]}"
            )
        return "Prior experiments (most recent last):\n" + "\n".join(lines)
