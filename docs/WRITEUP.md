# Building a harness that resists fooling itself

Most "AI finds alpha" projects are false-positive machines. Give a code-writing
model enough attempts and it will produce a backtest that looks spectacular and
generalizes to nothing. QuantResearchAgent is an attempt to take the interesting part
of that problem seriously: **not "can an agent find a strategy?" but "can a
harness let an agent search aggressively while staying statistically honest
about what it found?"**

## The shape of the system

An LLM agent runs a tool-calling loop - summarize the data, propose a
hypothesis, write a strategy module, backtest it, refine, submit. That loop is
the part people mean by "agent harness": a model gateway, a typed tool protocol,
context budgeting, and bounded iteration. None of it is coupled to trading; swap
the tools and it researches something else.

What makes it concrete - and not a toy - is everything *underneath* the loop.

## The simulator is a real matching engine

The backtest core is not a vectorized `returns.shift()`; it is an event-driven
market simulator built on a price-time-priority limit-order-book matching engine
(extended from a separate C++ project). It adds a clock, market orders, a
portfolio layer, and - the part that matters - a **queue-position fill model**.
A resting order only fills once the volume ahead of it has traded. Because the
engine matches FIFO at each price level, inserting our orders behind existing
liquidity gives the right queue position for free; replaying historical trades
as aggressive flow then fills us exactly when our turn comes.

A pure-Python reference implements the same semantics and serves as the
executable spec; the native C++ core (via nanobind) is the fast path, and a
parity test guarantees they produce identical equity curves. The Python/C++
boundary is crossed only at decision points, so throughput stays high.

## Integrity is structural, not aspirational

- **Partitioning**: every dataset is split TRAIN / VALIDATION / HOLDOUT along
  time, with an embargo gap.
- **Tool-level enforcement**: the agent's data tool physically cannot return
  holdout rows.
- **Network-deny sandbox**: agent code runs with no network, which is both a
  security control and a leakage guard (no fetching future data, no exfiltrating
  the holdout).
- **Holdout run by the harness**: only the frozen, submitted strategy is scored
  on the holdout - by the orchestrator, never inside the agent loop.

## The honest headline

When an agent generates hundreds of strategies, the best-looking holdout result
is a selection artifact unless you correct for the search. So the eval harness
computes the Probability of Backtest Overfitting (via combinatorially-symmetric
cross-validation), the Deflated Sharpe Ratio (correcting for the number of
trials, skew, and kurtosis), and a Benjamini-Hochberg FDR correction across the
whole population. A strategy is only reported as "surviving" if it beats
baselines on the holdout *and* clears corrected significance *and* has a high
deflated Sharpe.

The result you put on a resume is therefore not "X% returns." It is: *of N
strategies the agent generated, only M survived out of sample after
correction.* Most don't. That's the point - and it's exactly the signal that
distinguishes someone who builds agent infrastructure from someone who demos a
prompt.

## What I'd build next

- A second task domain on the same harness (the loop/tools/sandbox/eval are
  domain-agnostic).
- gVisor/Firecracker runtimes for the sandbox.
- Distributed orchestration to push parallel backtests/hour higher.
