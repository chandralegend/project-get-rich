# Compute benchmark: Mac mini M4, 16 GB

Run on 2026-11-14 with [scripts/bench_compute.py](../scripts/bench_compute.py). Raw results: [docs/benchmarks/m4-compute-2026-11-14.json](benchmarks/m4-compute-2026-11-14.json).

**Question:** which backend should train the small PI-Net market encoder, PyTorch on CPU, PyTorch on the Apple GPU (MPS), or MLX?

## Method

- Training throughput (forward, backward, Adam step) on random data of realistic shape: batch 256, 60 time steps, 8 features. Only speed is measured, never model quality.
- Two models: a 2-layer GRU (hidden 64, about 39k parameters) and a 4-layer Transformer encoder (width 128, about 0.8M parameters). These match the "small GRU / TCN" and "under 1M trainable parameters" targets in ARCHITECTURE.md.
- 5 warm-up steps, then 100 timed steps for the GRU and 50 for the Transformer, one run each in its own process.
- Versions: PyTorch 2.15.0 (MPS available), MLX 0.32.4, Python 3.13, macOS 26.5.

## Results

| Backend | Model | Steps/s | Samples/s | Peak RSS |
|---|---|---:|---:|---:|
| PyTorch CPU | GRU | 34.1 | 8,722 | 398 MiB |
| **PyTorch MPS** | GRU | **54.8** | **14,033** | 443 MiB |
| MLX | GRU | 12.6 | 3,236 | 56 MiB* |
| PyTorch CPU | Transformer | 6.5 | 1,654 | 794 MiB |
| PyTorch MPS | Transformer | 11.3 | 2,890 | 476 MiB |
| **MLX** | Transformer | **13.2** | **3,370** | 46 MiB* |
| LightGBM 4.7.0 | 500k rows × 60 features, 200 trees | 3.5 s per fit | | 448 MiB |

\* MLX allocates on the unified-memory GPU, and peak resident size as reported by the OS probably understates it. Do not read this column as an MLX memory advantage.

LightGBM first failed because its library needs `libomp`. After `brew install libomp` it was rerun on its own: a 200-tree fit on 500k × 60 random rows took 3.5 seconds, so a daily-bar model with a few thousand rows trains in well under a second.

## What it means

1. **Compute is not the bottleneck, data is.** At daily bars the plan has about 3.6k labelled events a year across 10 assets. Even the slowest case here (about 1.6k samples a second) trains a pass over ten years of events in a few seconds. The backend choice will not decide whether the project works.
2. **Default to PyTorch.** It was fastest for the GRU on MPS and competitive on the Transformer, and it has the widest library support. Use MPS for GRU or TCN encoders and plain CPU for anything tiny.
3. **MLX is no faster in general.** It matched the GPU path on the Transformer and was about 4× slower than PyTorch MPS on the GRU. Keep MLX for inference of ported foundation models (for example the Chronos-2 MLX port) rather than training.
4. **Memory is fine.** Every training run stayed under 800 MiB, well inside the roughly 8 GB usable for models.

## Caveats

- One run per case with no variance estimate. Differences under about 20% should not be trusted.
- The MLX GRU is probably handicapped by per-time-step graph overhead. I did not try `mx.compile`, which could change that result.
- Random data and a fixed batch shape. Real data loading, longer sequences and bigger batches are not covered.
- Throughput only. Nothing here says a model will predict anything.

## Open items

- Repeat after any macOS or PyTorch major update, since MPS performance has changed between releases.
- `getrich doctor` checks that `libomp` is present, because LightGBM will not load without it.
