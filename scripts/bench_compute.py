"""Compute benchmark for the Mac mini M4 (Phase 0 task: MPS vs MLX vs CPU).

Measures training throughput (forward + backward + Adam) of two small sequence models that match
the PI-Net market encoder, on three backends, plus LightGBM fit time. Each case runs in its own
subprocess so peak memory is isolated. Random data of realistic shape: only speed is measured,
never model quality.

Run (throwaway environment, nothing is added to the project):
  uv run --no-project --with torch --with mlx --with lightgbm --with numpy \
      python -I scripts/bench_compute.py --out /path/to/results.json
"""

from __future__ import annotations

import argparse
import json
import resource
import subprocess
import sys
import time

BATCH, SEQ, FEATS = 256, 60, 8
CASES = [
    ("torch-cpu", "gru"),
    ("torch-mps", "gru"),
    ("mlx", "gru"),
    ("torch-cpu", "transformer"),
    ("torch-mps", "transformer"),
    ("mlx", "transformer"),
    ("lightgbm", "gbm"),
]


def peak_rss_mib() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**20  # bytes on macOS


def bench_torch(device_name: str, model_name: str, steps: int) -> dict:
    import torch
    from torch import nn

    device = torch.device("mps" if device_name == "mps" else "cpu")
    torch.manual_seed(0)

    class GRUNet(nn.Module):
        def __init__(self):
            super().__init__()
            self.gru = nn.GRU(FEATS, 64, num_layers=2, batch_first=True)
            self.head = nn.Linear(64, 2)

        def forward(self, x):
            out, _ = self.gru(x)
            return self.head(out[:, -1])

    class TfNet(nn.Module):
        def __init__(self, d=128, layers=4, heads=4):
            super().__init__()
            self.inp = nn.Linear(FEATS, d)
            layer = nn.TransformerEncoderLayer(d, heads, 4 * d, dropout=0.0, batch_first=True)
            self.enc = nn.TransformerEncoder(layer, layers, enable_nested_tensor=False)
            self.head = nn.Linear(d, 2)

        def forward(self, x):
            return self.head(self.enc(self.inp(x)).mean(1))

    model = (GRUNet() if model_name == "gru" else TfNet()).to(device)
    params = sum(p.numel() for p in model.parameters())
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    loss_fn = nn.CrossEntropyLoss()
    x = torch.randn(BATCH, SEQ, FEATS, device=device)
    y = torch.randint(0, 2, (BATCH,), device=device)

    def sync():
        if device.type == "mps":
            torch.mps.synchronize()

    def step():
        opt.zero_grad()
        loss_fn(model(x), y).backward()
        opt.step()

    for _ in range(5):
        step()
    sync()
    t0 = time.perf_counter()
    for _ in range(steps):
        step()
    sync()
    dt = time.perf_counter() - t0
    return {"params": params, "steps_per_s": steps / dt, "samples_per_s": steps * BATCH / dt, "torch": torch.__version__}


def bench_mlx(model_name: str, steps: int) -> dict:
    import mlx.core as mx
    import mlx.nn as nn
    import mlx.optimizers as optim
    from mlx.utils import tree_flatten

    mx.random.seed(0)

    class GRUNet(nn.Module):
        def __init__(self):
            super().__init__()
            self.l1 = nn.GRU(FEATS, 64)
            self.l2 = nn.GRU(64, 64)
            self.head = nn.Linear(64, 2)

        def __call__(self, x):
            return self.head(self.l2(self.l1(x))[:, -1])

    class TfNet(nn.Module):
        def __init__(self, d=128, layers=4, heads=4):
            super().__init__()
            self.inp = nn.Linear(FEATS, d)
            self.enc = nn.TransformerEncoder(layers, d, heads, 4 * d, dropout=0.0)
            self.head = nn.Linear(d, 2)

        def __call__(self, x):
            return self.head(self.enc(self.inp(x), None).mean(1))

    model = GRUNet() if model_name == "gru" else TfNet()
    mx.eval(model.parameters())
    params = sum(v.size for _, v in tree_flatten(model.parameters()))
    opt = optim.Adam(learning_rate=1e-3)
    x = mx.random.normal((BATCH, SEQ, FEATS))
    y = mx.random.randint(0, 2, (BATCH,))

    def loss_fn(m, xb, yb):
        return nn.losses.cross_entropy(m(xb), yb, reduction="mean")

    loss_and_grad = nn.value_and_grad(model, loss_fn)

    def step():
        loss, grads = loss_and_grad(model, x, y)
        opt.update(model, grads)
        mx.eval(model.parameters(), opt.state, loss)

    for _ in range(5):
        step()
    t0 = time.perf_counter()
    for _ in range(steps):
        step()
    dt = time.perf_counter() - t0
    return {"params": params, "steps_per_s": steps / dt, "samples_per_s": steps * BATCH / dt, "mlx": mx.__version__ if hasattr(mx, "__version__") else "?"}


def bench_lightgbm() -> dict:
    import numpy as np

    try:
        import lightgbm as lgb
    except Exception as exc:  # most often: libomp missing on macOS
        return {"skipped": f"{type(exc).__name__}: {str(exc)[:200]}"}
    rng = np.random.default_rng(0)
    n, f = 500_000, 60
    X = rng.standard_normal((n, f), dtype=np.float32)
    y = (X[:, 0] + 0.5 * X[:, 1] + rng.standard_normal(n) > 0).astype(np.int32)
    ds = lgb.Dataset(X, label=y)
    t0 = time.perf_counter()
    lgb.train({"objective": "binary", "num_leaves": 31, "learning_rate": 0.05, "verbose": -1}, ds, num_boost_round=200)
    dt = time.perf_counter() - t0
    return {"rows": n, "features": f, "trees": 200, "fit_seconds": dt, "lightgbm": lgb.__version__}


def run_case(backend: str, model: str, steps: int) -> dict:
    if backend == "torch-cpu":
        res = bench_torch("cpu", model, steps)
    elif backend == "torch-mps":
        res = bench_torch("mps", model, steps)
    elif backend == "mlx":
        res = bench_mlx(model, steps)
    else:
        res = bench_lightgbm()
    res["peak_rss_mib"] = round(peak_rss_mib(), 0)
    return res


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--case", help="backend:model (internal, used for subprocess isolation)")
    p.add_argument("--steps", type=int, default=100)
    p.add_argument("--out")
    args = p.parse_args()

    if args.case:
        backend, model = args.case.split(":")
        try:
            print(json.dumps(run_case(backend, model, args.steps)))
        except Exception as exc:
            print(json.dumps({"error": f"{type(exc).__name__}: {str(exc)[:300]}"}))
        return 0

    results = []
    for backend, model in CASES:
        steps = args.steps if model == "gru" else max(args.steps // 2, 20)
        print(f"running {backend}:{model} ...", file=sys.stderr, flush=True)
        t0 = time.perf_counter()
        proc = subprocess.run(
            [sys.executable, "-I", __file__, "--case", f"{backend}:{model}", "--steps", str(steps)],
            capture_output=True, text=True,
        )
        line = (proc.stdout.strip().splitlines() or ["{}"])[-1]
        try:
            res = json.loads(line)
        except json.JSONDecodeError:
            res = {"error": (proc.stderr or proc.stdout)[-300:]}
        res.update(backend=backend, model=model, wall_s=round(time.perf_counter() - t0, 1))
        results.append(res)
        print("  ", res, file=sys.stderr, flush=True)
    if args.out:
        with open(args.out, "w") as f:
            json.dump(results, f, indent=2)
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
