"""Cost / token / latency ledger.

Wired into the model gateway via its usage callback. Accumulates per-run totals
and can persist each call to the store.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field


@dataclass
class CostLedger:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    latency_s: float = 0.0
    calls: int = 0
    cache_hits: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def record(
        self,
        provider: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        cost: float,
        cached: bool,
        latency: float,
    ) -> None:
        with self._lock:
            self.prompt_tokens += prompt_tokens
            self.completion_tokens += completion_tokens
            self.cost_usd += cost
            self.latency_s += latency
            self.calls += 1
            self.cache_hits += int(cached)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def summary(self) -> dict[str, float]:
        return {
            "calls": self.calls,
            "cache_hits": self.cache_hits,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "cost_usd": round(self.cost_usd, 6),
            "latency_s": round(self.latency_s, 3),
        }
