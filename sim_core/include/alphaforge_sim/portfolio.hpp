#pragma once
#include <cstdint>

#include "events.hpp"

namespace afsim {

// Position / cash / PnL accounting layered on top of the fill stream.
struct Portfolio {
    double tick_size = 0.01;
    double maker_fee_bps = 0.0;
    double taker_fee_bps = 0.0;

    long position = 0;
    double cash = 0.0;
    double fees_paid = 0.0;
    long traded_qty = 0;
    long n_trades = 0;

    void settle(int8_t side, int64_t price, int64_t qty, bool is_maker) {
        const int s = sign_of(side);
        position += static_cast<long>(s) * qty;
        cash -= static_cast<double>(s) * static_cast<double>(qty) *
                static_cast<double>(price) * tick_size;
        const double bps = is_maker ? maker_fee_bps : taker_fee_bps;
        const double fee =
            static_cast<double>(price) * tick_size * static_cast<double>(qty) * (bps / 10000.0);
        cash -= fee;
        fees_paid += fee;
        traded_qty += qty;
        ++n_trades;
    }

    [[nodiscard]] double equity(double mark) const {
        return cash + static_cast<double>(position) * mark * tick_size;
    }
};

}  // namespace afsim
