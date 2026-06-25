"""Hardened execution sandbox."""

from quant_research_agent.config import SandboxConfig

from .base import SandboxResult, SandboxRunner
from .docker_sandbox import DockerSandbox, docker_available
from .local_sandbox import LocalSandbox


def build_sandbox(cfg: SandboxConfig) -> SandboxRunner:
    """Pick the strongest available backend for the requested config."""
    if cfg.backend == "local":
        return LocalSandbox(cfg)
    if cfg.backend == "docker":
        return DockerSandbox(cfg)
    # auto
    if docker_available():
        return DockerSandbox(cfg)
    return LocalSandbox(cfg)


__all__ = [
    "DockerSandbox",
    "LocalSandbox",
    "SandboxConfig",
    "SandboxResult",
    "SandboxRunner",
    "build_sandbox",
    "docker_available",
]
