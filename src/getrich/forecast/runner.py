"""Run a forecaster in its own process and environment.

Why: every model package pins its own torch/transformers versions (granite-tsfm wants torch < 2.12, we run 2.15), PyTorch and
LightGBM cannot share a process on macOS, and Kronos ships third-party code that should never run inside the process that holds
the database and the API keys. The worker gets a numpy file in and writes a numpy file out. It runs with HF_HUB_OFFLINE=1, so it
can only use weights that `forecast-fetch` downloaded on purpose and recorded in the lock file; it can never fetch anything itself.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from .. import config
from .base import HORIZONS, QUANTILES, Forecaster

WORKERS = Path(__file__).parent / "workers"


@dataclass
class ModelSpec:
    name: str
    release: str                          # public release date: origins after it are free of pretraining contamination
    context_len: int
    worker: str                           # file in workers/
    requirements: list[str]               # pip requirements for the worker's throwaway environment
    repos: list[dict]                     # [{"repo": ..., "allow": [...]}] weights fetched by `forecast-fetch`
    stride: int = 1
    batch: int = 256
    timeout_s: int = 6 * 3600
    extra_args: list[str] = field(default_factory=list)
    note: str = ""


class SubprocessForecaster(Forecaster):
    def __init__(self, spec: ModelSpec, launcher: list[str] | None = None, env: dict | None = None):
        self.spec = spec
        self.name, self.context_len = spec.name, spec.context_len
        self.release = pd.Timestamp(spec.release, tz="UTC")
        self.default_stride, self.batch = spec.stride, spec.batch
        self._launcher = launcher                      # tests substitute a plain python; real runs use uv with the model's requirements
        self._env = env or {}
        self.last_diag: dict = {}

    def command(self, inp: Path, out: Path) -> list[str]:
        if self._launcher is not None:
            prefix = list(self._launcher)
        else:
            prefix = ["uv", "run", "--no-project", "--python", "3.13", *[a for r in self.spec.requirements for a in ("--with", r)], "python", "-I"]
        return [*prefix, str(WORKERS / self.spec.worker), str(inp), str(out), *self.spec.extra_args]

    def forecast(self, ohlcv: np.ndarray, ts: np.ndarray) -> np.ndarray:
        tmp = config.data_dir() / "forecasts" / "_tmp"
        tmp.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=tmp) as d:
            inp, out = Path(d) / "in.npz", Path(d) / "out.npz"
            np.savez(inp, ohlcv=ohlcv, ts=ts, horizons=np.array(HORIZONS), quantiles=np.array(QUANTILES))
            env = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "LANG", "TMPDIR", "UV_CACHE_DIR", "HF_HOME")}
            env.update({"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "PYTORCH_ENABLE_MPS_FALLBACK": "1", **self._env})
            proc = subprocess.run(self.command(inp, out), capture_output=True, text=True, timeout=self.spec.timeout_s, env=env, cwd=d)
            if proc.returncode != 0 or not out.exists():
                raise RuntimeError(f"{self.spec.name} worker failed (exit {proc.returncode}): {(proc.stderr or proc.stdout)[-600:]}")
            z = np.load(out)
            self.last_diag = {"invalid_paths": int(z["invalid_paths"].sum()), "origins_with_invalid_paths": int((z["invalid_paths"] > 0).sum())} if "invalid_paths" in z.files else {}
            return z["cube"]
