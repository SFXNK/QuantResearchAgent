// nanobind bindings for the Alphaforge market simulator.
//
// The Python layer passes events as parallel numpy arrays (cheap to marshal)
// and a single decision-point callback, so the Python/C++ boundary is crossed
// O(decision points) times instead of O(ticks).

#include <nanobind/nanobind.h>
#include <nanobind/ndarray.h>
#include <nanobind/stl/function.h>
#include <nanobind/stl/tuple.h>
#include <nanobind/stl/vector.h>

#include <cstdint>
#include <vector>

#include "alphaforge_sim/events.hpp"
#include "alphaforge_sim/simulator.hpp"

namespace nb = nanobind;
using namespace afsim;

namespace {

using ActionTuple = std::tuple<int8_t, int8_t, int64_t, int64_t, int64_t>;

}  // namespace

NB_MODULE(alphaforge_sim_native, m) {
    m.doc() = "Alphaforge native market simulator (extends HFTMatchingEngine).";

    nb::class_<RunResult>(m, "RunResult")
        .def_ro("equity", &RunResult::equity)
        .def_ro("timestamps", &RunResult::timestamps)
        .def_ro("n_trades", &RunResult::n_trades)
        .def_ro("turnover", &RunResult::turnover)
        .def_ro("final_position", &RunResult::final_position)
        .def_ro("fees_paid", &RunResult::fees_paid);

    nb::class_<MarketSimulator>(m, "MarketSimulator")
        .def(nb::init<double, int64_t, double, double, double>(), nb::arg("tick_size"),
             nb::arg("latency_ns"), nb::arg("maker_fee_bps"), nb::arg("taker_fee_bps"),
             nb::arg("impact_coeff"))
        .def(
            "load_events",
            [](MarketSimulator& self, nb::ndarray<int64_t, nb::ndim<1>> ts,
               nb::ndarray<int8_t, nb::ndim<1>> type, nb::ndarray<int8_t, nb::ndim<1>> side,
               nb::ndarray<int64_t, nb::ndim<1>> price, nb::ndarray<int64_t, nb::ndim<1>> qty,
               nb::ndarray<int64_t, nb::ndim<1>> order_id) {
                const size_t n = ts.shape(0);
                std::vector<MarketEvent> evs;
                evs.reserve(n);
                for (size_t i = 0; i < n; ++i) {
                    evs.push_back(MarketEvent{ts(i), type(i), side(i), price(i), qty(i),
                                              order_id(i)});
                }
                self.load_events(std::move(evs));
            },
            nb::arg("ts"), nb::arg("type"), nb::arg("side"), nb::arg("price"), nb::arg("qty"),
            nb::arg("order_id"))
        .def(
            "run",
            [](MarketSimulator& self, int64_t decision_interval_ns, nb::callable cb) {
                StrategyCallback wrapper = [&cb](int step, int64_t t, int64_t bid, int64_t ask,
                                                 long pos, double cash,
                                                 double eq) -> std::vector<Action> {
                    nb::object res = cb(step, t, bid, ask, pos, cash, eq);
                    std::vector<Action> actions;
                    for (nb::handle item : res) {
                        auto tup = nb::cast<ActionTuple>(item);
                        actions.push_back(Action{std::get<0>(tup), std::get<1>(tup),
                                                 std::get<2>(tup), std::get<3>(tup),
                                                 std::get<4>(tup)});
                    }
                    return actions;
                };
                return self.run(decision_interval_ns, wrapper);
            },
            nb::arg("decision_interval_ns"), nb::arg("callback"));
}
