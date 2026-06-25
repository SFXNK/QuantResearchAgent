"""The research agent: loop, journal memory, context budgeting."""

from .context import trim_to_budget
from .journal import Journal, JournalEntry
from .loop import AgentResult, ResearchAgent
from .prompts import SYSTEM_PROMPT

__all__ = [
    "SYSTEM_PROMPT",
    "AgentResult",
    "Journal",
    "JournalEntry",
    "ResearchAgent",
    "trim_to_budget",
]
