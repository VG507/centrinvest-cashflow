import math
import numpy as np
import pytest
from src.services.math.metrics import (
    compute_wape,
    compute_brier_score,
    murphy_brier_decomposition,
)
from src.services.math.fpt_solver import (
    wald_fpt_density,
    wald_gap_probability,
    compute_analytical_fpt,
    simulate_moving_block_bootstrap,
)
from src.services.math.conformal import (
    compute_empirical_coverage,
    calibrate_conformal_corridor,
)


class TestMetrics:
    def test_wape_scale_invariance(self):
        actual = np.array([100.0, 250.0, 0.0, 400.0, 50.0])
        predicted = np.array([120.0, 230.0, 20.0, 380.0, 60.0])

        wape_base = compute_wape(actual, predicted)
        assert wape_base is not None
        assert 0.0 < wape_base < 1.0

        # Scale by factor of 1000.0 (e.g. currency scale rubles to thousands)
        wape_scaled = compute_wape(actual * 1000.0, predicted * 1000.0)
        assert wape_scaled == wape_base

    def test_wape_handles_zero_revenue_days_without_division_by_zero(self):
        # 3 out of 5 days have zero revenue (weekends / quiet days)
        actual = np.array([0.0, 50000.0, 0.0, 0.0, 75000.0])
        predicted = np.array([1000.0, 48000.0, 500.0, 0.0, 80000.0])

        # Standard MAPE would divide by 0 and raise error/inf
        wape = compute_wape(actual, predicted)
        assert wape is not None
        # Hand calculation: total abs err = 1000 + 2000 + 500 + 0 + 5000 = 8500
        # total actual = 125000 -> 8500 / 125000 = 0.068
        assert abs(wape - 0.068) < 1e-4

    def test_wape_zero_turnover_returns_zero(self):
        actual = np.zeros(5)
        predicted = np.zeros(5)
        assert compute_wape(actual, predicted) == 0.0
        assert compute_wape(actual, np.full(5, 50.0)) == 1.0

    def test_brier_score_and_murphy_decomposition(self):
        probs = np.array([0.9, 0.8, 0.1, 0.2, 0.7, 0.05, 0.85, 0.15])
        outcomes = np.array([1.0, 1.0, 0.0, 0.0, 1.0, 0.0, 1.0, 0.0])

        bs = compute_brier_score(probs, outcomes)
        assert bs is not None
        assert bs < 0.1  # Highly accurate predictions

        decomp = murphy_brier_decomposition(probs, outcomes, num_bins=5)
        assert decomp is not None
        # Murphy decomposition identity: BS approx Reliability - Resolution + Uncertainty
        reconstructed = decomp["reliability"] - decomp["resolution"] + decomp["uncertainty"]
        assert abs(decomp["brier_score"] - reconstructed) < 0.05


class TestFPTSolver:
    def test_wald_fpt_density_positive_and_decays(self):
        initial_balance = 10000.0
        drift = -500.0  # Daily burn rate of 500 rubles
        sigma = 800.0

        # Mode around 20 days (10000 / 500)
        density_5 = wald_fpt_density(5.0, initial_balance, drift, sigma)
        density_20 = wald_fpt_density(20.0, initial_balance, drift, sigma)
        density_100 = wald_fpt_density(100.0, initial_balance, drift, sigma)

        assert density_20 > density_5
        assert density_20 > density_100
        assert density_20 > 0.0

    def test_wald_gap_probability_boundary_conditions(self):
        # Immediate gap if initial balance <= 0
        assert wald_gap_probability(30.0, 0.0, 100.0, 50.0) == 1.0
        assert wald_gap_probability(30.0, -1000.0, 100.0, 50.0) == 1.0

        # Highly solvent company with large positive drift: gap prob near 0
        p_safe = wald_gap_probability(30.0, 1000000.0, 10000.0, 500.0)
        assert p_safe < 1e-4

        # Company with severe negative burn: gap prob near 1
        p_danger = wald_gap_probability(60.0, 10000.0, -2000.0, 300.0)
        assert p_danger > 0.99

    def test_analytical_fpt_summary_structure(self):
        res = compute_analytical_fpt(
            initial_balance=50000.0,
            drift=-1000.0,
            sigma=2000.0,
            horizon_days=30
        )
        assert "ruin_probability" in res
        assert 0.0 <= res["ruin_probability"] <= 1.0
        assert res["instantaneous_hazard_horizon"] >= 0.0

    def test_moving_block_bootstrap_simulation(self):
        pred_inc = np.full(30, 1000.0)
        pred_exp = np.full(30, 900.0)
        # 40 days of history
        rng = np.random.default_rng(123)
        res_inc = rng.normal(0.0, 100.0, size=40)
        res_exp = rng.normal(0.0, 100.0, size=40)

        sim = simulate_moving_block_bootstrap(
            initial_balance=5000.0,
            pred_income=pred_inc,
            pred_expense=pred_exp,
            res_income=res_inc,
            res_expense=res_exp,
            n_samples=200,
            block_len=7,
            seed=42
        )

        assert sim["trajectories"].shape == (200, 30)
        assert len(sim["lower_bounds"]) == 30
        assert len(sim["upper_bounds"]) == 30
        assert np.all(sim["lower_bounds"] <= sim["upper_bounds"])
        assert 0.0 <= sim["cumulative_gap_probability"] <= 1.0


class TestConformalCalibration:
    def test_empirical_coverage_computation(self):
        actual = np.array([10.0, 20.0, 30.0, 40.0, 50.0])
        lower = np.array([5.0, 15.0, 25.0, 45.0, 45.0])  # 4th item fails (actual 40 < lower 45)
        upper = np.array([15.0, 25.0, 35.0, 55.0, 55.0])

        cov = compute_empirical_coverage(actual, lower, upper)
        # 4 out of 5 covered = 0.80
        assert cov == 0.80

    def test_calibrate_conformal_corridor_adjusts_bounds(self):
        pred_low = np.array([100.0, 100.0, 100.0])
        pred_upp = np.array([200.0, 200.0, 200.0])

        # Historical points with some violations
        h_act = np.array([90.0, 150.0, 210.0, 160.0, 140.0, 170.0, 205.0, 95.0, 150.0, 160.0])
        h_low = np.full(10, 100.0)
        h_upp = np.full(10, 200.0)

        res = calibrate_conformal_corridor(
            predicted_lower=pred_low,
            predicted_upper=pred_upp,
            historical_actual=h_act,
            historical_lower=h_low,
            historical_upper=h_upp,
            alpha=0.20
        )

        assert "calibrated_lower" in res
        assert "calibrated_upper" in res
        assert res["conformal_shift"] > 0.0  # Corridor expanded to cover violations
        assert np.all(res["calibrated_lower"] < pred_low)
        assert np.all(res["calibrated_upper"] > pred_upp)
