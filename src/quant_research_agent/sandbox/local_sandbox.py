"""Local (subprocess) sandbox fallback.

Used when Docker is unavailable (e.g. CI without a daemon, or quick local runs).
On POSIX it enforces resource limits via `setrlimit` (CPU time, address space,
process count, open files, file size) and, when possible, network isolation via
`unshare -n`. It is *not* a strong security boundary the way the Docker sandbox
is -- prefer Docker for untrusted code -- but it still contains the common
failure modes (runaway memory, fork bombs, infinite loops) and runs the exact
same entrypoint.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import quant_research_agent
from quant_research_agent.config import SandboxConfig

from .base import SandboxResult

_IS_POSIX = os.name == "posix"
_SRC_DIR = Path(quant_research_agent.__file__).resolve().parents[1]

if _IS_POSIX:
    import resource

    def _make_limiter(cfg: SandboxConfig):  # noqa: ANN202
        def _set_limits() -> None:
            mem = cfg.memory_mb * 1024 * 1024
            cpu = max(1, cfg.wall_timeout_s)
            resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
            resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu + 1))
            resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))
            resource.setrlimit(resource.RLIMIT_FSIZE, (64 * 1024 * 1024, 64 * 1024 * 1024))
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
            try:
                resource.setrlimit(resource.RLIMIT_NPROC, (cfg.pids_limit, cfg.pids_limit))
            except (ValueError, OSError):
                pass
            os.setsid()

        return _set_limits
else:  # pragma: no cover - Windows
    def _make_limiter(cfg: SandboxConfig):  # noqa: ANN202
        return None


def _net_prefix(cfg: SandboxConfig) -> list[str]:
    """Best-effort network isolation on Linux via user+net namespaces."""
    if cfg.network_disabled and _IS_POSIX and shutil.which("unshare"):
        return ["unshare", "--map-root-user", "--net", "--"]
    return []


class LocalSandbox:
    backend = "local"

    def __init__(self, cfg: SandboxConfig) -> None:
        self.cfg = cfg
        self._net = _net_prefix(cfg)
        self.network_disabled = bool(self._net) if cfg.network_disabled else False

    def _env(self) -> dict[str, str]:
        env = {
            "PYTHONPATH": str(_SRC_DIR),
            "PATH": os.environ.get("PATH", ""),
            "PYTHONDONTWRITEBYTECODE": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "OMP_NUM_THREADS": "1",
        }
        if _IS_POSIX:
            env["HOME"] = "/tmp"
        else:
            # Windows needs these for the C runtime / Winsock / temp to initialize.
            for key in (
                "SystemRoot", "windir", "SystemDrive", "TEMP", "TMP", "USERPROFILE",
                "NUMBER_OF_PROCESSORS", "PATHEXT", "ComSpec", "APPDATA", "LOCALAPPDATA",
            ):
                val = os.environ.get(key)
                if val:
                    env[key] = val
        return env

    def run_python(self, args: list[str], workspace: Path) -> SandboxResult:
        cmd = [*self._net, sys.executable, *args]
        start = time.perf_counter()
        timed_out = False
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(workspace),
                env=self._env(),
                capture_output=True,
                text=True,
                timeout=self.cfg.wall_timeout_s,
                preexec_fn=_make_limiter(self.cfg) if _IS_POSIX else None,
                check=False,
            )
            returncode, stdout, stderr = proc.returncode, proc.stdout, proc.stderr
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            returncode = 124
            stdout = exc.stdout or "" if isinstance(exc.stdout, str) else ""
            stderr = "timeout"
        duration = time.perf_counter() - start
        return SandboxResult(returncode, stdout, stderr, timed_out, duration)

    def run_code(self, code: str, workspace: Path) -> SandboxResult:
        """Run an arbitrary snippet under the same limits (used by the security suite)."""
        script = workspace / "_snippet.py"
        script.write_text(code)
        return self.run_python([str(script)], workspace)

    def run_backtest(
        self,
        strategy_path: Path,
        events_path: Path,
        sim_config_path: Path,
        interval: int,
        out_path: Path,
    ) -> SandboxResult:
        args = [
            "-m",
            "quant_research_agent.research.runner",
            "--strategy", str(strategy_path),
            "--events", str(events_path),
            "--sim-config", str(sim_config_path),
            "--interval", str(interval),
            "--out", str(out_path),
        ]
        return self.run_python(args, out_path.parent)
