# external/

Third-party code vendored as git submodules. Nothing here is modified.

## HFTMatchingEngine

The deterministic, price-time-priority limit-order-book matching engine that the
QuantResearchAgent sim core (`sim_core/`) extends. Pulled in as a submodule:

```bash
git submodule update --init --recursive
```

This populates `external/HFTMatchingEngine/` with `defs.h`, `orderbook.h`,
`memory_pool.h`, and `lockfree_queue.h`. The sim core includes `defs.h`
(integer-tick types) and `memory_pool.h` (the zero-allocation slab allocator)
directly, and conceptually extends `orderbook.h` with a clock, market orders,
queue-position fills, and a portfolio layer. The original repository is left
untouched.
