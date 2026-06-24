"""Pure-Python reference market simulator.

This is the executable specification for the native C++ core. It reconstructs a
price-time-priority limit order book from the event stream and models fills for
the strategy's own orders by *queue position*: a resting order only fills once
the volume that was ahead of it at its price level has traded. That is the part
naive vectorized backtesters get wrong, and it is why fills here are honest.

Performance is intentionally secondary to clarity; the native core exists for
throughput and is checked against this implementation for parity.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Sequence

import numpy as np

from alphaforge.config import SimConfig
from alphaforge.types import BacktestResult, EventType, Fill, MarketEvent, Side

from .base import ActionKind, Observation, StrategyFn

_MARKET_OWNER = 0


class _Node:
    """A FIFO entry at a price level. owner==0 means anonymous market liquidity."""

    __slots__ = ("qty", "owner")

    def __init__(self, qty: int, owner: int) -> None:
        self.qty = qty
        self.owner = owner


class _Book:
    """Reconstructed L2 book with per-level FIFO queues tagged by owner."""

    def __init__(self) -> None:
        # side -> price -> deque[_Node]
        self.levels: dict[Side, dict[int, deque[_Node]]] = {Side.BUY: {}, Side.SELL: {}}
        self.market_nodes: dict[int, _Node] = {}  # external order id -> node
        self.our_nodes: dict[int, tuple[Side, int, _Node]] = {}  # our id -> (side, price, node)

    def _level(self, side: Side, price: int) -> deque[_Node]:
        book = self.levels[side]
        dq = book.get(price)
        if dq is None:
            dq = deque()
            book[price] = dq
        return dq

    def add_market(self, side: Side, price: int, qty: int, ext_id: int) -> None:
        node = _Node(qty, _MARKET_OWNER)
        self._level(side, price).append(node)
        if ext_id:
            self.market_nodes[ext_id] = node

    def add_ours(self, side: Side, price: int, qty: int, order_id: int) -> None:
        node = _Node(qty, order_id)
        self._level(side, price).append(node)  # behind existing volume -> correct queue pos
        self.our_nodes[order_id] = (side, price, node)

    def cancel_external(self, ext_id: int) -> None:
        node = self.market_nodes.pop(ext_id, None)
        if node is not None:
            node.qty = 0

    def cancel_ours(self, order_id: int) -> None:
        rec = self.our_nodes.pop(order_id, None)
        if rec is not None:
            rec[2].qty = 0

    def best(self, side: Side) -> int | None:
        prices = [p for p, dq in self.levels[side].items() if sum(n.qty for n in dq) > 0]
        if not prices:
            return None
        return max(prices) if side is Side.BUY else min(prices)

    def best_bid(self) -> int | None:
        return self.best(Side.BUY)

    def best_ask(self) -> int | None:
        return self.best(Side.SELL)


class PythonSimCore:
    """Reference implementation of the `SimCore` protocol."""

    def run(
        self,
        events: Sequence[MarketEvent],
        strategy: StrategyFn,
        config: SimConfig,
        decision_interval_ns: int,
    ) -> BacktestResult:
        book = _Book()
        position = 0
        cash = 0.0
        fees_paid = 0.0
        traded_qty = 0
        n_trades = 0
        tick = config.tick_size

        equity_curve: list[float] = []
        ts_curve: list[int] = []

        def apply_fee(price: int, qty: int, is_maker: bool) -> None:
            nonlocal cash, fees_paid
            bps = config.maker_fee_bps if is_maker else config.taker_fee_bps
            fee = price * tick * qty * (bps / 10_000.0)
            cash -= fee
            fees_paid += fee

        def settle(side: Side, price: int, qty: int, is_maker: bool) -> None:
            nonlocal position, cash, traded_qty, n_trades
            position += side.sign * qty
            cash -= side.sign * qty * price * tick
            apply_fee(price, qty, is_maker)
            traded_qty += qty
            n_trades += 1

        def consume(resting_side: Side, price: int, qty: int) -> int:
            """Consume `qty` from the front of a resting level. Our fills settle as maker.

            Returns the quantity actually consumed.
            """
            dq = book.levels[resting_side].get(price)
            if dq is None:
                return 0
            remaining = qty
            while remaining > 0 and dq:
                node = dq[0]
                if node.qty <= 0:
                    dq.popleft()
                    continue
                take = min(remaining, node.qty)
                node.qty -= take
                remaining -= take
                if node.owner != _MARKET_OWNER:
                    settle(resting_side, price, take, is_maker=True)
                    if node.qty == 0:
                        book.our_nodes.pop(node.owner, None)
                if node.qty == 0:
                    dq.popleft()
            return qty - remaining

        def apply_event(ev: MarketEvent) -> None:
            if ev.type is EventType.ADD:
                book.add_market(ev.side, ev.price, ev.qty, ev.order_id)
            elif ev.type is EventType.CANCEL:
                book.cancel_external(ev.order_id)
            elif ev.type is EventType.TRADE:
                # ev.side is the aggressor; it consumes the opposite resting side.
                consume(ev.side.opposite, ev.price, ev.qty)

        def cross_or_rest(side: Side, price: int, qty: int, order_id: int) -> None:
            """Place a strategy limit order: match marketable part as taker, rest the remainder."""
            opp = side.opposite
            remaining = qty
            while remaining > 0:
                best_opp = book.best(opp)
                if best_opp is None:
                    break
                crosses = price >= best_opp if side is Side.BUY else price <= best_opp
                if not crosses:
                    break
                filled = consume(opp, best_opp, remaining)
                if filled == 0:
                    break
                settle(side, best_opp, filled, is_maker=False)  # we are the aggressor here
                remaining -= filled
            if remaining > 0:
                book.add_ours(side, price, remaining, order_id)

        def market_order(side: Side, qty: int) -> None:
            """Walk the opposite book as a taker, applying linear temporary impact."""
            opp = side.opposite
            remaining = qty
            depth = 0
            while remaining > 0:
                best_opp = book.best(opp)
                if best_opp is None:
                    break
                filled = consume(opp, best_opp, remaining)
                if filled == 0:
                    break
                impact_ticks = config.impact_coeff * depth
                eff_price = best_opp + side.sign * impact_ticks
                settle(side, round(eff_price), filled, is_maker=False)
                remaining -= filled
                depth += filled

        def equity_now() -> float:
            bb, ba = book.best_bid(), book.best_ask()
            if bb is not None and ba is not None:
                mark = (bb + ba) / 2.0
            elif bb is not None:
                mark = float(bb)
            elif ba is not None:
                mark = float(ba)
            else:
                mark = 0.0
            return cash + position * mark * tick

        if not events:
            return BacktestResult(
                equity=np.zeros(0),
                returns=np.zeros(0),
                timestamps=np.zeros(0, dtype=np.int64),
                n_trades=0,
                turnover=0.0,
                final_position=0,
                fees_paid=0.0,
            )

        sorted_events = sorted(events, key=lambda e: e.ts)
        idx = 0
        n = len(sorted_events)
        start_ts = sorted_events[0].ts
        end_ts = sorted_events[-1].ts
        step = 0
        decision_ts = start_ts

        while decision_ts <= end_ts:
            while idx < n and sorted_events[idx].ts <= decision_ts:
                apply_event(sorted_events[idx])
                idx += 1

            obs = Observation(
                step=step,
                ts=decision_ts,
                best_bid=book.best_bid(),
                best_ask=book.best_ask(),
                position=position,
                cash=cash,
                equity=equity_now(),
            )
            for action in strategy(obs):
                if action.kind is ActionKind.LIMIT:
                    cross_or_rest(action.side, action.price, action.qty, action.order_id)
                elif action.kind is ActionKind.MARKET:
                    market_order(action.side, action.qty)
                elif action.kind is ActionKind.CANCEL:
                    book.cancel_ours(action.order_id)

            equity_curve.append(equity_now())
            ts_curve.append(decision_ts)
            step += 1
            decision_ts += decision_interval_ns

        equity = np.asarray(equity_curve, dtype=np.float64)
        if equity.shape[0] > 1:
            prev = equity[:-1]
            with np.errstate(divide="ignore", invalid="ignore"):
                returns = np.where(np.abs(prev) > 1e-12, np.diff(equity) / prev, 0.0)
        else:
            returns = np.zeros(0, dtype=np.float64)

        avg_equity = float(np.mean(np.abs(equity))) if equity.shape[0] else 1.0

        return BacktestResult(
            equity=equity,
            returns=returns,
            timestamps=np.asarray(ts_curve, dtype=np.int64),
            n_trades=n_trades,
            turnover=float(traded_qty),
            final_position=position,
            fees_paid=fees_paid,
            meta={"avg_equity": avg_equity},
        )


# Used by the parity test as the discriminator id of "our" orders.
_ = Fill  # re-exported type marker for callers building fills downstream
