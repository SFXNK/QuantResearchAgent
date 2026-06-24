"""Hardened Docker sandbox (defense in depth).

Each backtest runs in a fresh, throwaway container with:
- no network (`network_mode=none`) -> also a data-leakage guard;
- non-root execution as the host uid/gid (writes stay owned by the user);
- all Linux capabilities dropped + no-new-privileges;
- a restrictive seccomp profile (`seccomp.json`);
- read-only root filesystem, a small tmpfs, and only the workspace mounted rw;
- cgroup CPU / memory / PID limits;
- a wall-clock timeout enforced by the host.

The package source is mounted read-only and exposed via PYTHONPATH, so the
image only needs a Python interpreter + numpy/polars/pydantic.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import alphaforge
from alphaforge.config import SandboxConfig

from .base import SandboxResult

try:  # pragma: no cover - optional dependency
    import docker
    from docker.types import Ulimit
except Exception:  # noqa: BLE001
    docker = None  # type: ignore[assignment]
    Ulimit = None  # type: ignore[assignment, misc]

_SECCOMP = (Path(__file__).parent / "seccomp.json").read_text()
_SRC_DIR = Path(alphaforge.__file__).resolve().parents[1]


def docker_available() -> bool:
    if docker is None:
        return False
    try:  # pragma: no cover - depends on a running daemon
        docker.from_env().ping()
        return True
    except Exception:  # noqa: BLE001
        return False


class DockerSandbox:
    backend = "docker"

    def __init__(self, cfg: SandboxConfig) -> None:
        if docker is None:  # pragma: no cover
            raise RuntimeError("docker SDK not installed; pip install 'alphaforge[sandbox]'")
        self.cfg = cfg
        self.network_disabled = cfg.network_disabled
        self._client = docker.from_env()

    def run_backtest(
        self,
        strategy_path: Path,
        events_path: Path,
        sim_config_path: Path,
        interval: int,
        out_path: Path,
    ) -> SandboxResult:  # pragma: no cover - requires docker daemon
        workspace = out_path.parent.resolve()

        def in_work(p: Path) -> str:
            return f"/work/{Path(p).resolve().relative_to(workspace)}"

        command = [
            "python",
            "-m",
            "alphaforge.research.runner",
            "--strategy", in_work(strategy_path),
            "--events", in_work(events_path),
            "--sim-config", in_work(sim_config_path),
            "--interval", str(interval),
            "--out", in_work(out_path),
        ]

        uid = os.getuid() if hasattr(os, "getuid") else 0
        gid = os.getgid() if hasattr(os, "getgid") else 0

        container = self._client.containers.run(
            image=self.cfg.image,
            command=command,
            detach=True,
            network_mode="none" if self.cfg.network_disabled else "bridge",
            mem_limit=f"{self.cfg.memory_mb}m",
            memswap_limit=f"{self.cfg.memory_mb}m",
            nano_cpus=int(self.cfg.cpu_limit * 1e9),
            pids_limit=self.cfg.pids_limit,
            read_only=True,
            tmpfs={"/tmp": "size=64m,noexec"},
            user=f"{uid}:{gid}",
            cap_drop=["ALL"],
            security_opt=["no-new-privileges:true", f"seccomp={_SECCOMP}"],
            environment={
                "PYTHONPATH": "/app/src",
                "HOME": "/tmp",
                "PYTHONDONTWRITEBYTECODE": "1",
                "OPENBLAS_NUM_THREADS": "1",
                "OMP_NUM_THREADS": "1",
            },
            working_dir="/work",
            volumes={
                str(_SRC_DIR): {"bind": "/app/src", "mode": "ro"},
                str(workspace): {"bind": "/work", "mode": "rw"},
            },
            ulimits=[Ulimit(name="nproc", soft=self.cfg.pids_limit, hard=self.cfg.pids_limit)]
            if Ulimit is not None
            else None,
        )

        start = time.perf_counter()
        timed_out = False
        try:
            result = container.wait(timeout=self.cfg.wall_timeout_s)
            returncode = int(result.get("StatusCode", 1))
        except Exception:  # noqa: BLE001 - timeout / daemon error
            timed_out = True
            returncode = 124
            try:
                container.kill()
            except Exception:  # noqa: BLE001
                pass
        duration = time.perf_counter() - start

        try:
            stdout = container.logs(stdout=True, stderr=False).decode(errors="replace")
            stderr = container.logs(stdout=False, stderr=True).decode(errors="replace")
        except Exception:  # noqa: BLE001
            stdout, stderr = "", ""
        finally:
            try:
                container.remove(force=True)
            except Exception:  # noqa: BLE001
                pass

        return SandboxResult(returncode, stdout, stderr, timed_out, duration)
