"""The PI-Net fusion network (ARCHITECTURE.md 4.3), v1: market, forecast and context channels.

  each channel -> its own small encoder -> a gate per channel (and a presence mask) -> concatenate
  -> trunk -> four heads: p (logit), e (expected net R), and two dense AUXILIARY heads
     (next-day return in sigma units, next-day log realised variance) that give the encoders far more
     supervision than the sparse trade outcomes alone.

A channel whose inputs are NaN is masked out (its encoder output is zeroed and the gate sees it as absent).
That is how the Claude-insight channel will be switched off until it has history. In v1 every channel is present.

Hyperparameters are fixed in advance, training uses a fixed number of epochs (no early stopping on any
evaluation data), and predictions average a few seeds. None of it is tuned on results.
"""

from __future__ import annotations

import numpy as np
import torch
from torch import nn

from .pinet import R_CLIP


class _Net(nn.Module):
    def __init__(self, idx: dict[str, list[int]], d: int, dropout: float):
        super().__init__()
        self.idx = idx
        self.names = list(idx)
        self.enc = nn.ModuleDict(
            {k: nn.Sequential(nn.Linear(len(v), d), nn.GELU(), nn.Dropout(dropout)) for k, v in idx.items()}
        )
        self.gate = nn.Linear(d * len(idx) + len(idx), len(idx))
        self.trunk = nn.Sequential(nn.Linear(d * len(idx), d), nn.GELU(), nn.Dropout(dropout))
        self.head_p, self.head_e = nn.Linear(d, 1), nn.Linear(d, 1)
        self.head_aux = nn.Linear(d, 2)

    def forward(self, x: torch.Tensor, present: torch.Tensor):
        hs = [self.enc[k](x[:, self.idx[k]]) * present[:, i : i + 1] for i, k in enumerate(self.names)]
        gates = torch.sigmoid(self.gate(torch.cat(hs + [present], dim=1)))
        z = torch.cat([h * gates[:, i : i + 1] for i, h in enumerate(hs)], dim=1)
        t = self.trunk(z)
        return self.head_p(t).squeeze(-1), self.head_e(t).squeeze(-1), self.head_aux(t)


class FusionPI:
    def __init__(self, idx: dict[str, list[int]], d: int = 32, dropout: float = 0.2, epochs: int = 30, lr: float = 2e-3,
                 weight_decay: float = 1e-3, batch: int = 256, seeds: tuple[int, ...] = (0, 1, 2), aux_weight: float = 0.3):
        self.idx, self.d, self.dropout, self.epochs = idx, d, dropout, epochs
        self.lr, self.wd, self.batch, self.seeds, self.aux_weight = lr, weight_decay, batch, seeds, aux_weight

    def _prep(self, X: np.ndarray):
        Z = (X.astype(np.float32) - self.mu) / self.sd
        present = np.stack([~np.isnan(Z[:, self.idx[k]]).any(axis=1) for k in self.idx], axis=1).astype(np.float32)
        return torch.from_numpy(np.nan_to_num(Z).astype(np.float32)), torch.from_numpy(present)

    def fit(self, X, y, r, aux=None):
        torch.set_num_threads(4)
        self.mu, self.sd = np.nanmean(X, 0, keepdims=True), np.nanstd(X, 0, keepdims=True) + 1e-6
        x, present = self._prep(X)
        yt = torch.from_numpy(np.asarray(y, dtype=np.float32))
        rt = torch.from_numpy(np.clip(r, *R_CLIP).astype(np.float32))
        if aux is not None:
            a = np.asarray(aux, dtype=np.float32).copy()
            self.aux_mu, self.aux_sd = np.nanmean(a[:, 1]), np.nanstd(a[:, 1]) + 1e-6
            a[:, 1] = (a[:, 1] - self.aux_mu) / self.aux_sd
            aux_t, aux_ok = torch.from_numpy(np.nan_to_num(a)), torch.from_numpy(~np.isnan(a))
        self.nets = []
        for seed in self.seeds:
            torch.manual_seed(seed)
            net = _Net(self.idx, self.d, self.dropout)
            opt = torch.optim.AdamW(net.parameters(), lr=self.lr, weight_decay=self.wd)
            gen = torch.Generator().manual_seed(seed)
            for _ in range(self.epochs):
                net.train()
                for b in torch.randperm(len(x), generator=gen).split(self.batch):
                    p, e, ax = net(x[b], present[b])
                    loss = nn.functional.binary_cross_entropy_with_logits(p, yt[b]) + nn.functional.mse_loss(e, rt[b])
                    if aux is not None:
                        ok = aux_ok[b]
                        if ok.any():
                            loss = loss + self.aux_weight * (((ax - aux_t[b]) ** 2) * ok).sum() / ok.sum()
                    opt.zero_grad()
                    loss.backward()
                    opt.step()
            net.eval()
            self.nets.append(net)
        return self

    def predict(self, X):
        x, present = self._prep(X)
        outs = []
        with torch.no_grad():
            for net in self.nets:
                p, e, _ = net(x, present)
                outs.append(np.column_stack([torch.sigmoid(p).numpy(), e.numpy()]))
        return np.mean(outs, axis=0)
