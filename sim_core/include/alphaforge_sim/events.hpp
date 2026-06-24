#pragma once
#include <cstdint>

// Event and action wire-types shared with the Python layer. Side encoding
// matches the vendored engine's `Side` enum (Buy = 0, Sell = 1).
namespace afsim {

enum class EvType : int8_t { Add = 0, Cancel = 1, Trade = 2 };
enum class ActionKind : int8_t { Limit = 0, Market = 1, Cancel = 2 };

inline int8_t opposite(int8_t side) { return side == 0 ? 1 : 0; }
inline int sign_of(int8_t side) { return side == 0 ? 1 : -1; }

struct MarketEvent {
    int64_t ts;
    int8_t type;
    int8_t side;
    int64_t price;
    int64_t qty;
    int64_t order_id;
};

struct Action {
    int8_t kind;
    int8_t side;
    int64_t price;
    int64_t qty;
    int64_t order_id;
};

}  // namespace afsim
