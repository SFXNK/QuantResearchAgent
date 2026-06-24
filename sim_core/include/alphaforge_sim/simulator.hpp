#pragma once
#include <algorithm>
#include <cstdint>
#include <deque>
#include <functional>
#include <unordered_map>
#include <vector>

#include "events.hpp"
#include "portfolio.hpp"

// Reuse the vendored engine's primitives. `defs.h` gives us the integer-tick
// `Price`/`Side` types and `Order` layout; `memory_pool.h` gives us the
// zero-allocation slab allocator we reuse on the hot path. The original
// `OrderBook` (orderbook.h) is the conceptual matching kernel this simulator
// extends with a clock, market orders, queue-position fills, and a portfolio.
#include "defs.h"
#include "memory_pool.h"

namespace afsim {

constexpr int64_t MARKET_OWNER = 0;
constexpr size_t NODE_POOL = 1u << 20;

struct Node {
    int64_t qty = 0;
    int64_t owner = MARKET_OWNER;
    void reset() {
        qty = 0;
        owner = MARKET_OWNER;
    }
};

struct RunResult {
    std::vector<double> equity;
    std::vector<int64_t> timestamps;
    long n_trades = 0;
    double turnover = 0.0;
    long final_position = 0;
    double fees_paid = 0.0;
};

// Callback invoked at each decision point; returns the strategy's desired
// actions. The hot replay loop stays in C++; Python is entered only here.
using StrategyCallback = std::function<std::vector<Action>(
    int /*step*/, int64_t /*ts*/, int64_t /*bid*/, int64_t /*ask*/, long /*pos*/, double /*cash*/,
    double /*equity*/)>;

class MarketSimulator {
public:
    MarketSimulator(double tick_size, int64_t latency_ns, double maker_fee_bps,
                    double taker_fee_bps, double impact_coeff)
        : latency_ns_(latency_ns), impact_coeff_(impact_coeff) {
        pf_.tick_size = tick_size;
        pf_.maker_fee_bps = maker_fee_bps;
        pf_.taker_fee_bps = taker_fee_bps;
    }

    void load_events(std::vector<MarketEvent> events) {
        events_ = std::move(events);
        std::stable_sort(events_.begin(), events_.end(),
                         [](const MarketEvent& a, const MarketEvent& b) { return a.ts < b.ts; });
    }

    RunResult run(int64_t decision_interval_ns, const StrategyCallback& strategy) {
        RunResult out;
        if (events_.empty()) return out;

        size_t idx = 0;
        const size_t n = events_.size();
        const int64_t start_ts = events_.front().ts;
        const int64_t end_ts = events_.back().ts;
        int step = 0;

        for (int64_t decision_ts = start_ts; decision_ts <= end_ts;
             decision_ts += decision_interval_ns) {
            while (idx < n && events_[idx].ts <= decision_ts) {
                apply_event(events_[idx]);
                ++idx;
            }

            const int64_t bid = best(0);
            const int64_t ask = best(1);
            const double eq = pf_.equity(mark(bid, ask));

            auto actions = strategy(step, decision_ts, bid, ask, pf_.position, pf_.cash, eq);
            for (const auto& a : actions) apply_action(a);

            out.equity.push_back(pf_.equity(mark(best(0), best(1))));
            out.timestamps.push_back(decision_ts);
            ++step;
        }

        out.n_trades = pf_.n_trades;
        out.turnover = static_cast<double>(pf_.traded_qty);
        out.final_position = pf_.position;
        out.fees_paid = pf_.fees_paid;
        (void)latency_ns_;  // reserved for sub-decision latency modeling
        return out;
    }

private:
    Portfolio pf_;
    int64_t latency_ns_;
    double impact_coeff_;
    std::vector<MarketEvent> events_;

    ObjectPool<Node, NODE_POOL> pool_;
    std::unordered_map<int64_t, std::deque<Node*>> book_[2];  // [side][price] -> FIFO
    std::unordered_map<int64_t, Node*> market_nodes_;
    std::unordered_map<int64_t, Node*> our_nodes_;

    [[nodiscard]] double mark(int64_t bid, int64_t ask) const {
        if (bid >= 0 && ask >= 0) return (static_cast<double>(bid) + static_cast<double>(ask)) / 2.0;
        if (bid >= 0) return static_cast<double>(bid);
        if (ask >= 0) return static_cast<double>(ask);
        return 0.0;
    }

    int64_t best(int8_t side) const {
        int64_t best_p = -1;
        for (const auto& [price, dq] : book_[side]) {
            int64_t vol = 0;
            for (const Node* nd : dq) vol += nd->qty;
            if (vol <= 0) continue;
            if (best_p < 0)
                best_p = price;
            else if (side == 0)
                best_p = std::max(best_p, price);
            else
                best_p = std::min(best_p, price);
        }
        return best_p;
    }

    Node* make_node(int64_t qty, int64_t owner) {
        Node* nd = pool_.allocate();
        nd->qty = qty;
        nd->owner = owner;
        return nd;
    }

    int64_t consume(int8_t resting_side, int64_t price, int64_t qty) {
        auto it = book_[resting_side].find(price);
        if (it == book_[resting_side].end()) return 0;
        auto& dq = it->second;
        int64_t remaining = qty;
        while (remaining > 0 && !dq.empty()) {
            Node* nd = dq.front();
            if (nd->qty <= 0) {
                dq.pop_front();
                pool_.deallocate(nd);
                continue;
            }
            const int64_t take = std::min(remaining, nd->qty);
            nd->qty -= take;
            remaining -= take;
            if (nd->owner != MARKET_OWNER) {
                pf_.settle(resting_side, price, take, /*is_maker=*/true);
                if (nd->qty == 0) our_nodes_.erase(nd->owner);
            }
            if (nd->qty == 0) {
                dq.pop_front();
                pool_.deallocate(nd);
            }
        }
        return qty - remaining;
    }

    void apply_event(const MarketEvent& ev) {
        switch (static_cast<EvType>(ev.type)) {
            case EvType::Add: {
                Node* nd = make_node(ev.qty, MARKET_OWNER);
                book_[ev.side][ev.price].push_back(nd);
                if (ev.order_id) market_nodes_[ev.order_id] = nd;
                break;
            }
            case EvType::Cancel: {
                auto it = market_nodes_.find(ev.order_id);
                if (it != market_nodes_.end()) it->second->qty = 0;
                break;
            }
            case EvType::Trade:
                consume(opposite(ev.side), ev.price, ev.qty);
                break;
        }
    }

    void place_limit(int8_t side, int64_t price, int64_t qty, int64_t order_id) {
        const int8_t opp = opposite(side);
        int64_t remaining = qty;
        while (remaining > 0) {
            const int64_t best_opp = best(opp);
            if (best_opp < 0) break;
            const bool crosses = side == 0 ? price >= best_opp : price <= best_opp;
            if (!crosses) break;
            const int64_t filled = consume(opp, best_opp, remaining);
            if (filled == 0) break;
            pf_.settle(side, best_opp, filled, /*is_maker=*/false);
            remaining -= filled;
        }
        if (remaining > 0) {
            Node* nd = make_node(remaining, order_id);
            book_[side][price].push_back(nd);
            our_nodes_[order_id] = nd;
        }
    }

    void place_market(int8_t side, int64_t qty) {
        const int8_t opp = opposite(side);
        int64_t remaining = qty;
        int64_t depth = 0;
        while (remaining > 0) {
            const int64_t best_opp = best(opp);
            if (best_opp < 0) break;
            const int64_t filled = consume(opp, best_opp, remaining);
            if (filled == 0) break;
            const double eff =
                static_cast<double>(best_opp) + sign_of(side) * impact_coeff_ * static_cast<double>(depth);
            pf_.settle(side, static_cast<int64_t>(eff + 0.5), filled, /*is_maker=*/false);
            remaining -= filled;
            depth += filled;
        }
    }

    void cancel_ours(int64_t order_id) {
        auto it = our_nodes_.find(order_id);
        if (it != our_nodes_.end()) {
            it->second->qty = 0;
            our_nodes_.erase(it);
        }
    }

    void apply_action(const Action& a) {
        switch (static_cast<ActionKind>(a.kind)) {
            case ActionKind::Limit:
                place_limit(a.side, a.price, a.qty, a.order_id);
                break;
            case ActionKind::Market:
                place_market(a.side, a.qty);
                break;
            case ActionKind::Cancel:
                cancel_ours(a.order_id);
                break;
        }
    }
};

}  // namespace afsim
