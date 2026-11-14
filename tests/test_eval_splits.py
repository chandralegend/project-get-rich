import numpy as np
import pytest

from getrich.eval import splits

DAY = np.timedelta64(1, "D")


def _samples(n=600, horizon_days=10):
    t0 = np.datetime64("2021-01-01") + np.arange(n) * DAY
    return t0, t0 + horizon_days * DAY


def _assert_no_leak(t0, t1, train, test, embargo):
    """The two leakage rules, checked directly against the definitions."""
    for start, end in [(t0[b[0]], t1[b].max()) for b in splits._blocks(test)]:
        overlapping = (t0[train] <= end) & (t1[train] >= start)
        assert not overlapping.any(), "a training label window overlaps a test block"
        in_embargo = (t0[train] > end) & (t0[train] <= end + embargo)
        assert not in_embargo.any(), "a training sample starts inside the embargo"


def test_kfold_tests_are_disjoint_and_cover_everything():
    t0, t1 = _samples()
    seen = np.concatenate([test for _, test in splits.PurgedKFold(5).split(t0, t1)])
    assert sorted(seen) == list(range(len(t0)))


@pytest.mark.parametrize("embargo_days", [0, 5, 15])
def test_kfold_never_leaks(embargo_days):
    t0, t1 = _samples()
    emb = embargo_days * DAY
    for train, test in splits.PurgedKFold(6, embargo=emb).split(t0, t1):
        assert len(np.intersect1d(train, test)) == 0
        _assert_no_leak(t0, t1, train, test, emb)


def test_a_naive_split_would_leak_on_the_same_data():
    # control: the same data with NO purge does have overlapping labels, so the check above has teeth
    t0, t1 = _samples()
    test = np.arange(100, 200)
    naive_train = np.setdiff1d(np.arange(len(t0)), test)
    with pytest.raises(AssertionError):
        _assert_no_leak(t0, t1, naive_train, test, np.timedelta64(0, "D"))


def test_without_overlap_or_embargo_purging_removes_nothing():
    t0, t1 = _samples(horizon_days=0)
    for train, test in splits.PurgedKFold(4).split(t0, t1):
        assert len(train) + len(test) == len(t0)


def test_purging_removes_about_the_horizon_on_each_side():
    t0, t1 = _samples(n=600, horizon_days=10)
    train, test = next(iter(splits.PurgedKFold(5, embargo=5 * DAY).split(t0, t1)))
    removed = len(t0) - len(train) - len(test)
    assert 10 <= removed <= 20  # purge of the labels reaching into the first test block, plus the embargo after it


def test_walk_forward_trains_only_on_resolved_labels_and_moves_forward():
    t0, t1 = _samples()
    last_test_start = -1
    for train, test in splits.walk_forward(t0, t1, n_splits=4, min_train_frac=0.4, embargo=2 * DAY):
        assert t1[train].max() < t0[test[0]] - 2 * DAY
        assert test[0] > last_test_start
        last_test_start = test[0]
        assert train.max() < test[0]


def test_cpcv_counts_match_the_formula():
    cv = splits.CombinatorialPurgedCV(6, 2)
    assert cv.n_splits == 15 and cv.n_paths == 5
    cv = splits.CombinatorialPurgedCV(8, 3)
    assert cv.n_splits == 56 and cv.n_paths == 21


def test_cpcv_never_leaks_and_train_test_are_disjoint():
    t0, t1 = _samples(n=720)
    emb = 4 * DAY
    cv = splits.CombinatorialPurgedCV(6, 2, embargo=emb)
    n = 0
    for train, test in cv.split(t0, t1):
        n += 1
        assert len(np.intersect1d(train, test)) == 0
        _assert_no_leak(t0, t1, train, test, emb)
    assert n == 15


def test_every_cpcv_path_covers_each_group_exactly_once():
    cv = splits.CombinatorialPurgedCV(6, 2)
    paths = cv.paths()
    assert len(paths) == cv.n_paths
    for path in paths:
        assert sorted(g for _, g in path) == list(range(6))
        for split_idx, g in path:
            assert g in cv.combos[split_idx]  # the split used for a group really tested that group
    # every (split, group) pair is used by exactly one path
    used = [pair for path in paths for pair in path]
    assert len(used) == len(set(used))


def test_group_of_labels_every_sample():
    cv = splits.CombinatorialPurgedCV(5, 2)
    g = cv.group_of(103)
    assert g.min() == 0 and g.max() == 4 and len(g) == 103


def test_bad_arguments_are_rejected():
    with pytest.raises(ValueError):
        splits.PurgedKFold(1)
    with pytest.raises(ValueError):
        splits.CombinatorialPurgedCV(4, 4)
