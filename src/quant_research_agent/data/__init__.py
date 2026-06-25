"""Data layer: partitioned, point-in-time datasets from synthetic or crypto sources."""

from quant_research_agent.config import DataConfig

from .crypto_l2 import frame_to_events, load_l2, normalize_frame
from .dataset import Dataset, LeakageError, PartitionBounds
from .partition import partition_events
from .synthetic import generate_synthetic, is_efficient_market


def load_dataset(cfg: DataConfig, seed: int) -> Dataset:
    """Dispatch to the configured data source."""
    if cfg.source == "synthetic":
        return generate_synthetic(cfg, seed)
    if cfg.source == "crypto_l2":
        if not cfg.path:
            raise ValueError("crypto_l2 source requires data.path (a CSV/Parquet file)")
        return load_l2(cfg.path, cfg, cfg.tick_size)
    raise ValueError(f"unknown data source {cfg.source!r}")


__all__ = [
    "DataConfig",
    "Dataset",
    "LeakageError",
    "PartitionBounds",
    "frame_to_events",
    "generate_synthetic",
    "is_efficient_market",
    "load_dataset",
    "load_l2",
    "normalize_frame",
    "partition_events",
]
