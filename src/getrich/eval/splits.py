"""Cross-validation splitters for overlapping financial labels.

A label that looks `h` days ahead overlaps its neighbours, so an ordinary shuffled K-fold leaks the test
period into training. These splitters fix that with two rules (Lopez de Prado, Advances in Financial ML):

  purge:   drop every training sample whose label window [t0, t1] overlaps a test block's span;
  embargo: also drop training samples that START within `embargo` after a test block ends.

All splitters take samples sorted by start time: `t0` (when the sample was decided) and `t1` (when its
label resolved), both numpy datetime64 arrays.

  PurgedKFold                 one test block per fold
  walk_forward                expanding train window, test always after train
  CombinatorialPurgedCV       every combination of k test groups out of N; assembles several full
                              out-of-sample "paths", which gives a DISTRIBUTION of scores, not one number
"""

from __future__ import annotations

from itertools import combinations
from math import comb

import numpy as np

Index = np.ndarray


def _blocks(test_idx: Index) -> list[Index]:
    """Split sorted test indices into runs of consecutive integers."""
    test_idx = np.sort(test_idx)
    cuts = np.where(np.diff(test_idx) > 1)[0] + 1
    return np.split(test_idx, cuts)


def purged_train_indices(t0, t1, test_idx: Index, embargo) -> Index:
    t0, t1 = np.asarray(t0), np.asarray(t1)
    embargo = np.timedelta64(embargo) if not isinstance(embargo, np.timedelta64) else embargo
    keep = np.ones(len(t0), dtype=bool)
    keep[test_idx] = False
    for block in _blocks(test_idx):
        start, end = t0[block[0]], t1[block].max()
        keep &= ~((t0 <= end) & (t1 >= start))          # purge: label window overlaps the test span
        keep &= ~((t0 > end) & (t0 <= end + embargo))    # embargo: starts just after the test span
    return np.where(keep)[0]


class PurgedKFold:
    def __init__(self, n_splits: int = 5, embargo=np.timedelta64(0, "D")):
        if n_splits < 2:
            raise ValueError("n_splits must be at least 2")
        self.n_splits, self.embargo = n_splits, np.timedelta64(embargo)

    def split(self, t0, t1):
        for test_idx in np.array_split(np.arange(len(t0)), self.n_splits):
            yield purged_train_indices(t0, t1, test_idx, self.embargo), test_idx


def walk_forward(t0, t1, n_splits: int = 5, min_train_frac: float = 0.3, embargo=np.timedelta64(0, "D")):
    """Expanding window. Train on samples whose labels were fully resolved before the test block began."""
    t0, t1 = np.asarray(t0), np.asarray(t1)
    embargo = np.timedelta64(embargo)
    n = len(t0)
    first_test = int(n * min_train_frac)
    for test_idx in np.array_split(np.arange(first_test, n), n_splits):
        if len(test_idx) == 0:
            continue
        test_start = t0[test_idx[0]]
        train = np.where(t1 < test_start - embargo)[0]
        yield train, test_idx


class CombinatorialPurgedCV:
    """N contiguous groups; each split holds out k of them (all C(N, k) choices) and trains on the rest,
    purged and embargoed. Each group is tested in C(N-1, k-1) splits, which can be stitched into that many
    complete out-of-sample paths."""

    def __init__(self, n_groups: int = 6, n_test_groups: int = 2, embargo=np.timedelta64(0, "D")):
        if not 1 <= n_test_groups < n_groups:
            raise ValueError("need 1 <= n_test_groups < n_groups")
        self.n_groups, self.k, self.embargo = n_groups, n_test_groups, np.timedelta64(embargo)
        self.combos = list(combinations(range(n_groups), n_test_groups))

    @property
    def n_splits(self) -> int:
        return comb(self.n_groups, self.k)

    @property
    def n_paths(self) -> int:
        return self.n_splits * self.k // self.n_groups

    def groups(self, n_samples: int) -> list[Index]:
        return np.array_split(np.arange(n_samples), self.n_groups)

    def group_of(self, n_samples: int) -> Index:
        out = np.empty(n_samples, dtype=int)
        for g, idx in enumerate(self.groups(n_samples)):
            out[idx] = g
        return out

    def split(self, t0, t1):
        groups = self.groups(len(t0))
        for combo in self.combos:
            test_idx = np.concatenate([groups[g] for g in combo])
            yield purged_train_indices(t0, t1, test_idx, self.embargo), np.sort(test_idx)

    def paths(self) -> list[list[tuple[int, int]]]:
        """Each path is a list of (split_index, group) pairs covering every group exactly once."""
        per_group = {g: [s for s, combo in enumerate(self.combos) if g in combo] for g in range(self.n_groups)}
        return [[(per_group[g][j], g) for g in range(self.n_groups)] for j in range(self.n_paths)]
