import math

import numpy as np
import pytest

from getrich.eval import metrics
from getrich.eval.costs import CostModel


def test_cost_model_round_trip_and_stress():
    c = CostModel(fee_bps=10, slippage_bps=5)
    assert c.one_way() == pytest.approx(0.0015)
    assert c.round_trip() == pytest.approx(0.0030)
    assert c.stressed(2).round_trip() == pytest.approx(0.0060)
    assert c.cost_in_r(0.05) == pytest.approx(0.06)  # 30 bps against a 5% stop is 0.06R


def test_cost_in_r_rejects_a_zero_stop():
    with pytest.raises(ValueError):
        CostModel().cost_in_r(0)


def test_sharpe_basics():
    assert math.isnan(metrics.sharpe([0.01, 0.01, 0.01]))  # zero variance
    r = np.array([0.01, -0.01, 0.02, 0.0, 0.01])
    assert metrics.sharpe(r, 365) == pytest.approx(r.mean() / r.std(ddof=1) * math.sqrt(365))


def test_max_drawdown_on_a_known_path():
    # +10% then -20% then +5%: peak 1.10, trough 0.88 -> drawdown 20%
    assert metrics.max_drawdown([0.10, -0.20, 0.05]) == pytest.approx(0.20)
    assert metrics.max_drawdown([0.01, 0.01]) == 0.0
    assert metrics.max_drawdown([-0.5]) == pytest.approx(0.5)  # a fall from the starting equity counts


def test_cagr_and_calmar():
    r = [0.001] * 365
    assert metrics.cagr(r, 365) == pytest.approx(1.001**365 - 1)
    assert math.isnan(metrics.calmar(r, 365))  # no drawdown


def test_probabilistic_sharpe_matches_a_hand_computation():
    # sr=0.1, n=101, normal returns: z = 0.1*10/sqrt(1.005) = 0.9975, cdf = 0.8407
    assert metrics.probabilistic_sharpe(0.1, 0.0, 101) == pytest.approx(0.8407, abs=0.001)


def test_probabilistic_sharpe_is_half_at_the_benchmark_and_grows_with_n():
    assert metrics.probabilistic_sharpe(0.05, 0.05, 500) == pytest.approx(0.5)
    assert metrics.probabilistic_sharpe(0.05, 0.0, 1000) > metrics.probabilistic_sharpe(0.05, 0.0, 100)


def test_expected_max_sharpe_matches_a_hand_computation():
    # n=10, var=0.01: 0.1 * (0.42278*1.28155 + 0.57722*1.7899) = 0.1575
    assert metrics.expected_max_sharpe(10, 0.01) == pytest.approx(0.1575, abs=0.001)
    assert metrics.expected_max_sharpe(1, 0.01) == 0.0


def test_expected_max_sharpe_grows_with_trials():
    values = [metrics.expected_max_sharpe(n, 0.01) for n in (2, 10, 100, 1000)]
    assert values == sorted(values)


def test_deflated_sharpe_falls_as_more_variants_are_tried():
    rng = np.random.default_rng(1)
    r = rng.normal(0.0008, 0.01, 1500)
    sr = r.mean() / r.std(ddof=1)
    few = metrics.deflated_sharpe(r, [sr, sr * 0.5])
    many = metrics.deflated_sharpe(r, list(sr * rng.uniform(-1, 1, 200)) + [sr])
    assert many < few


def test_deflated_sharpe_single_trial_equals_psr_against_zero():
    rng = np.random.default_rng(2)
    r = rng.normal(0.001, 0.01, 800)
    sr = r.mean() / r.std(ddof=1)
    skew, kurt = metrics._moments(r)
    assert metrics.deflated_sharpe(r, [sr]) == pytest.approx(metrics.probabilistic_sharpe(sr, 0.0, len(r), skew, kurt))


def test_a_pure_noise_strategy_does_not_survive_deflation():
    rng = np.random.default_rng(3)
    noise = [rng.normal(0, 0.01, 1000) for _ in range(50)]
    sharpes = [x.mean() / x.std(ddof=1) for x in noise]
    best = noise[int(np.argmax(sharpes))]
    # the best of 50 coin-flip strategies looks good on its own but not after deflation
    assert metrics.deflated_sharpe(best, sharpes) < 0.95
