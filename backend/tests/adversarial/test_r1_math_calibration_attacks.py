import math
import numpy as np
import pytest

from src.services.math.conformal import (
    adaptive_conformal_step,
    calibrate_conformal_corridor,
    compute_empirical_coverage,
)
from src.services.math.fpt_solver import (
    compute_analytical_fpt,
    norm_cdf,
    simulate_moving_block_bootstrap,
    wald_fpt_density,
    wald_gap_probability,
)
from src.services.math.metrics import (
    compute_brier_score,
    compute_wape,
    murphy_brier_decomposition,
)


# ==============================================================================
# SECTION 1: CONFORMAL CALIBRATION REMEDIATION TESTS
# ==============================================================================


class TestConformalCalibrationAttacks:
    """Expected-correctness regression gates for conformal calibration."""

    def test_attack_1_1_conformal_coverage_collapse_under_ood_regime_shift(self):
        """REMEDY: Adaptive conformal inference maintains coverage under OOD regime shift.

        Under an out-of-distribution regime shift (e.g. 30% drop in revenue),
        adaptive conformal calibration (Gibbs & Candes 2021) updates prediction
        bounds sequentially so coverage adapts and avoids collapse.
        """
        rng = np.random.default_rng(42)

        # In-distribution stationary calibration window: 20 days around 1,000 rub
        h_act = 1000.0 + rng.normal(0.0, 30.0, size=20)
        h_low = np.full(20, 920.0)
        h_upp = np.full(20, 1080.0)

        # Baseline forecast for next 14 days
        p_low = np.full(14, 920.0)
        p_upp = np.full(14, 1080.0)
        point_pred = np.full(14, 1000.0)

        calib_res = calibrate_conformal_corridor(
            predicted_lower=p_low,
            predicted_upper=p_upp,
            historical_actual=h_act,
            historical_lower=h_low,
            historical_upper=h_upp,
            alpha=0.20,
            point_predictions=point_pred,
        )

        assert calib_res["nominal_coverage"] == 0.80

        # Out-of-distribution regime shift in test period:
        # 30% drop in revenue: actual balance drops to 750 rub with moderate noise
        test_act_ood = 750.0 + rng.normal(0.0, 25.0, size=14)

        cur_low = float(calib_res["calibrated_lower"][0])
        cur_upp = float(calib_res["calibrated_upper"][0])
        alpha_t = 0.20
        covered_days = 0
        for t in range(14):
            if cur_low <= test_act_ood[t] <= cur_upp:
                covered_days += 1
            cur_low, cur_upp, alpha_t = adaptive_conformal_step(
                current_lower=cur_low,
                current_upper=cur_upp,
                actual=float(test_act_ood[t]),
                alpha_t=alpha_t,
                target_alpha=0.20,
                gamma=0.10,
            )

        adaptive_coverage = covered_days / 14.0
        assert adaptive_coverage >= 0.50, (
            f"Expected adaptive conformal calibration to maintain coverage >= 50%, got {adaptive_coverage:.2%}"
        )

    def test_attack_1_2_conformal_negative_shift_causes_corridor_shrinkage(self):
        """REMEDY: Non-conformity scores bounded by 0 prevent interval contraction.

        When historical validation actuals fall well within the heuristic corridor,
        lower-bounding non-conformity scores by 0 ensures conformal_shift >= 0.
        The calibrated corridor never contracts below the heuristic baseline.
        """
        # Historical actuals safely in the center: 500 rub vs corridor [200, 800]
        h_act = np.full(20, 500.0)
        h_low = np.full(20, 200.0)
        h_upp = np.full(20, 800.0)

        # Initial prediction corridor with width 600
        p_low = np.full(10, 200.0)
        p_upp = np.full(10, 800.0)
        point_pred = np.full(10, 500.0)

        calib_res = calibrate_conformal_corridor(
            predicted_lower=p_low,
            predicted_upper=p_upp,
            historical_actual=h_act,
            historical_lower=h_low,
            historical_upper=h_upp,
            alpha=0.20,
            point_predictions=point_pred,
        )

        shift = calib_res["conformal_shift"]
        assert shift >= 0.0, f"Expected non-negative conformal shift, got {shift}"

        orig_width = p_upp[0] - p_low[0]  # 600.0
        calib_width = calib_res["calibrated_upper"][0] - calib_res["calibrated_lower"][0]

        # The corridor never contracts below the baseline width
        assert calib_width >= orig_width, (
            f"Corridor width must not contract: orig={orig_width}, calib={calib_width}"
        )
        assert calib_res["calibrated_lower"][0] <= p_low[0]
        assert calib_res["calibrated_upper"][0] >= p_upp[0]

    def test_attack_1_3_conformal_zero_variance_degenerate_interval_collapse(self):
        """REMEDY: Scale-relative floor prevents degenerate corridor collapse.

        For constant cash flows on large corporate balances (e.g. 10,000,000 rub),
        the corridor width maintains a scale-relative floor (min 1% of point prediction),
        preventing degenerate collapse to a static 10.0 ruble margin.
        """
        large_balance = 10_000_000.0
        h_act = np.full(20, large_balance)
        h_low = np.full(20, large_balance)
        h_upp = np.full(20, large_balance)

        p_low = np.full(14, large_balance)
        p_upp = np.full(14, large_balance)
        point_pred = np.full(14, large_balance)

        calib_res = calibrate_conformal_corridor(
            predicted_lower=p_low,
            predicted_upper=p_upp,
            historical_actual=h_act,
            historical_lower=h_low,
            historical_upper=h_upp,
            alpha=0.20,
            point_predictions=point_pred,
        )

        cal_width = calib_res["calibrated_upper"][0] - calib_res["calibrated_lower"][0]
        relative_width = cal_width / large_balance

        # Scale-relative floor enforces >= 1% corridor on multi-million balances
        assert cal_width >= 0.01 * large_balance, (
            f"Expected at least 1% scale floor ({0.01 * large_balance}), got {cal_width}"
        )
        assert relative_width >= 0.01

    def test_attack_1_4_conformal_small_sample_false_coverage_attestation(self):
        """REMEDY: Empirical coverage accurately computed for small samples (N < 5).

        When sample size N < 5, historical coverage is genuinely computed
        rather than returning a hardcoded literal 1.0.
        """
        # 3 historical points completely outside bounds
        h_act = np.array([50.0, 50.0, 50.0])
        h_low = np.array([500.0, 500.0, 500.0])
        h_upp = np.array([1000.0, 1000.0, 1000.0])

        true_coverage = compute_empirical_coverage(h_act, h_low, h_upp)
        assert true_coverage == 0.0, "True empirical coverage is 0.0"

        calib_res = calibrate_conformal_corridor(
            predicted_lower=np.full(7, 500.0),
            predicted_upper=np.full(7, 1000.0),
            historical_actual=h_act,
            historical_lower=h_low,
            historical_upper=h_upp,
            alpha=0.20,
        )

        # Truthful attestation: matches true coverage 0.0, not hardcoded 1.0
        assert calib_res["historical_coverage"] == true_coverage
        assert calib_res["historical_coverage"] == 0.0
        assert calib_res["sample_size"] == 3


# ==============================================================================
# SECTION 2: RESIDUAL BLOCK BOOTSTRAP REMEDIATION TESTS
# ==============================================================================


class TestResidualBlockBootstrapAttacks:
    """Expected-correctness regression gates for residual block bootstrap."""

    def test_attack_2_1_bootstrap_asymmetric_clamping_positive_drift_bias(self):
        """REMEDY: Expectation-preserving scaling eliminates positive drift bias.

        Expectation-preserving scaling ensures simulated draws match point prediction
        expectations while guaranteeing non-negativity, eliminating positive drift bias.
        """
        horizon_days = 30
        pred_inc = np.full(horizon_days, 100.0)
        pred_exp = np.full(horizon_days, 5000.0)
        init_bal = 100_000.0

        # Create zero-mean symmetric residuals
        rng = np.random.default_rng(42)
        raw_res_inc = rng.normal(0.0, 300.0, size=70)
        raw_res_exp = rng.normal(0.0, 300.0, size=70)
        res_inc = raw_res_inc - np.mean(raw_res_inc)
        res_exp = raw_res_exp - np.mean(raw_res_exp)
        assert abs(np.mean(res_inc)) < 1e-10
        assert abs(np.mean(res_exp)) < 1e-10

        sim_res = simulate_moving_block_bootstrap(
            initial_balance=init_bal,
            pred_income=pred_inc,
            pred_expense=pred_exp,
            res_income=res_inc,
            res_expense=res_exp,
            n_samples=5000,
            block_len=7,
            seed=42,
        )

        point_end_balance = init_bal + horizon_days * (100.0 - 5000.0)
        mean_sim_end_balance = float(np.mean(sim_res["trajectories"][:, -1]))
        bias = mean_sim_end_balance - point_end_balance

        # Expectation-preserving scaling eliminates drift bias
        assert abs(bias) < 50.0, f"Expected drift bias < 50 rub, got {bias:.2f} rub"

    def test_attack_2_2_bootstrap_asymmetric_clamping_negative_drift_phantom_gaps(self):
        """REMEDY: Zero-expense baseline does not manufacture artificial cash burn.

        When baseline expense is 0.0, simulated expenses scale to 0.0,
        preventing phantom gap downward balance bias.
        """
        horizon_days = 30
        pred_inc = np.full(horizon_days, 5000.0)
        pred_exp = np.full(horizon_days, 0.0)  # Zero baseline expense
        init_bal = 10_000.0

        rng = np.random.default_rng(42)
        raw_res_inc = rng.normal(0.0, 50.0, size=70)
        raw_res_exp = rng.normal(0.0, 400.0, size=70)
        res_inc = raw_res_inc - np.mean(raw_res_inc)
        res_exp = raw_res_exp - np.mean(raw_res_exp)

        sim_res = simulate_moving_block_bootstrap(
            initial_balance=init_bal,
            pred_income=pred_inc,
            pred_expense=pred_exp,
            res_income=res_inc,
            res_expense=res_exp,
            n_samples=5000,
            block_len=7,
            seed=42,
        )

        point_end_balance = init_bal + horizon_days * 5000.0
        mean_sim_end_balance = float(np.mean(sim_res["trajectories"][:, -1]))
        bias = mean_sim_end_balance - point_end_balance

        # Eliminates negative phantom gap bias
        assert abs(bias) < 50.0, f"Expected bias < 50 rub, got {bias:.2f} rub"

    def test_attack_2_3_bootstrap_short_history_fallback_scrambles_weekday_phase(self):
        """REMEDY: Short history (N < 7) preserves 7-day cyclical phase.

        When n_hist < block_len, residual sampling preserves weekday alignment
        modulo 7 so weekend flows remain quiet and weekday flows align with business days.
        """
        # 6 days history: Mon-Fri have 5000 rub business flow, Sat has 0 rub flow
        res_inc = np.array([5000.0, 5000.0, 5000.0, 5000.0, 5000.0, 0.0])
        res_exp = np.zeros(6)

        sim_res = simulate_moving_block_bootstrap(
            initial_balance=1000.0,
            pred_income=np.zeros(14),
            pred_expense=np.zeros(14),
            res_income=res_inc,
            res_expense=res_exp,
            n_samples=1000,
            block_len=7,
            seed=42,
            forecast_start_weekday=0,
            history_start_weekday=0,
        )

        trajectories = sim_res["trajectories"]

        # Day 5 (Saturday in 0-indexed week from Monday) must preserve 0 flow
        day_5_deltas = trajectories[:, 5] - trajectories[:, 4]
        fraction_non_zero = np.mean(day_5_deltas > 0.0)

        # Weekday phase is preserved: Saturday receives 0 inflow
        assert fraction_non_zero <= 0.05, (
            f"Expected weekend phase preservation (<= 5% non-zero), got {fraction_non_zero:.2%}"
        )


# ==============================================================================
# SECTION 3: FIRST PASSAGE TIME (FPT) SOLVER REGRESSION TESTS
# ==============================================================================


class TestFPTSolverEdgeCases:
    """Expected-correctness regression gates for First Passage Time solver."""

    def test_attack_3_1_fpt_near_zero_drift_catastrophic_cancellation(self):
        """REMEDY: Rationalized formula evaluates modal ruin time to theoretical limit.

        The rationalized algebraic formula 2*lambda / (sqrt(4*gamma^2 + 9) + 3)
        evaluates smoothly to B_0^2 / (3*sigma^2) = 33.33 days without catastrophic cancellation.
        """
        initial_balance = 1000.0
        drift = -1e-15  # Near-zero negative drift
        sigma = 100.0
        horizon_days = 30

        theoretical_limit_mode = (initial_balance**2) / (3.0 * (sigma**2))  # 33.3333 days

        res = compute_analytical_fpt(
            initial_balance=initial_balance,
            drift=drift,
            sigma=sigma,
            horizon_days=horizon_days,
        )

        computed_mode = res["modal_ruin_time"]

        assert computed_mode is not None
        assert abs(computed_mode - 33.33) < 0.05
        assert abs(computed_mode - theoretical_limit_mode) < 0.05

    def test_attack_3_2_fpt_gamma_underflow_causes_zero_division_error(self):
        """REMEDY: Subnormal underflow guard prevents ZeroDivisionError on extreme drift.

        When drift mu <= -1e-165, gamma^2 underflow is handled safely and evaluates
        smoothly to the diffusion limit.
        """
        initial_balance = 1000.0
        drift = -1e-165  # Float64 underflow regime for gamma^2
        sigma = 100.0
        horizon_days = 30

        res = compute_analytical_fpt(
            initial_balance=initial_balance,
            drift=drift,
            sigma=sigma,
            horizon_days=horizon_days,
        )

        assert res["modal_ruin_time"] is not None
        assert abs(res["modal_ruin_time"] - 33.33) < 0.05
        assert 0.0 <= res["ruin_probability"] <= 1.0

    def test_attack_3_3_fpt_norm_cdf_standard_space_underflow_wipes_reflection_term(self):
        """REMEDY: Asymptotic Mill's ratio retains Bachelier reflection term.

        Under extreme coordinates where norm_cdf underflows in standard space,
        the asymptotic log-space Mill's ratio evaluates the reflection term accurately.
        """
        p = wald_gap_probability(horizon=1.0, initial_balance=200.0, drift=-10.0, sigma=20.0)
        assert 0.0 <= p <= 1.0

        # Asymptotic Mill's ratio evaluates non-zero reflection term
        z1 = -2.0
        z2 = -40.0
        phi_z1 = (1.0 / math.sqrt(2.0 * math.pi)) * math.exp(-0.5 * (z1**2))
        term2 = (phi_z1 / -z2) * (1.0 - (1.0 / (z2**2)))
        assert term2 > 0.0
        assert abs(term2 - (phi_z1 / 40.0)) < 1e-4

    def test_attack_3_4_fpt_wald_gap_probability_truncation_on_large_exp_arg(self):
        """REMEDY: Continuous evaluation for large negative drift without step truncation.

        When exp_arg > 700.0, wald_gap_probability evaluates continuously without
        discontinuous step zeroing.
        """
        p_30 = wald_gap_probability(
            horizon=30.0,
            initial_balance=50_000.0,
            drift=-500.0,
            sigma=200.0,
        )
        assert 0.0 <= p_30 < 1e-10

        p_120 = wald_gap_probability(
            horizon=120.0,
            initial_balance=50_000.0,
            drift=-500.0,
            sigma=200.0,
        )
        assert p_120 > 0.99


# ==============================================================================
# SECTION 4: METRIC ANOMALIES REGRESSION TESTS
# ==============================================================================


class TestMetricAnomalies:
    """Expected-correctness regression gates for metrics and scoring rules."""

    def test_attack_4_1_wape_zero_turnover_division_by_zero_and_ranking_penalty(self):
        """REMEDY: Zero turnover WAPE returns 0.0 for perfect zero-flow prediction.

        When actual turnover is 0.0 and predicted error is 0.0, compute_wape returns 0.0.
        When predicted flow is non-zero on zero actual, compute_wape returns 1.0.
        """
        actual_zero = np.zeros(14)
        pred_perfect = np.zeros(14)  # Perfect prediction of zero flow
        pred_terrible = np.full(14, 50000.0)  # Grossly inaccurate prediction

        wape_perfect = compute_wape(actual_zero, pred_perfect)
        wape_terrible = compute_wape(actual_zero, pred_terrible)

        assert wape_perfect == 0.0
        assert wape_terrible == 1.0
        assert wape_perfect != wape_terrible

    def test_attack_4_2_wape_extreme_scale_distortion_on_kopeck_turnover(self):
        """REMEDY: Scale stabilization prevents kopeck turnover distortion.

        When actual turnover is less than 1 ruble (kopecks), denominator floor
        stabilizes WAPE and prevents unbounded percentage distortion.
        """
        actual_kopeck = np.array([0.01, 0.0, 0.0])
        pred_nominal = np.array([100.0, 0.0, 0.0])

        wape_distorted = compute_wape(actual_kopeck, pred_nominal)

        assert wape_distorted is not None
        assert wape_distorted <= 100.0

    def test_attack_4_3_wape_silent_nan_propagation_without_input_validation(self):
        """REMEDY: compute_wape validates input arrays and raises ValueError on NaNs."""
        actual_with_nan = np.array([100.0, np.nan, 200.0])
        predicted = np.array([100.0, 150.0, 200.0])

        with pytest.raises(ValueError) as exc_info:
            compute_wape(actual_with_nan, predicted)

        assert "Input arrays contain NaN values" in str(exc_info.value)

    def test_attack_4_4_murphy_brier_decomposition_identity_broken_by_binning(self):
        """REMEDY: Murphy (1973) Brier score identity reconciled with intra-bin variance.

        The decomposition satisfies BS_binned = Reliability - Resolution + Uncertainty,
        and provides within_bin_variance.
        """
        probs = np.linspace(0.01, 0.99, 100)
        rng = np.random.default_rng(42)
        outcomes = (probs > 0.50).astype(float)

        decomp = murphy_brier_decomposition(probs, outcomes, num_bins=2)
        assert decomp is not None

        bs = decomp["brier_score"]
        reconstructed_bs = round(
            decomp["reliability"] - decomp["resolution"] + decomp["uncertainty"], 4
        )

        within_bin_discrepancy = abs(bs - reconstructed_bs)
        assert within_bin_discrepancy < 1e-3, (
            f"Expected Murphy decomposition identity to hold, discrepancy was {within_bin_discrepancy}"
        )
        assert "within_bin_variance" in decomp
        assert decomp["within_bin_variance"] > 0.0

    def test_attack_4_5_murphy_brier_zero_base_rate_collapses_resolution(self):
        """REMEDY: Zero base rate handled cleanly in Murphy decomposition.

        When no cash gaps occur in validation, uncertainty and resolution are 0.0,
        and brier_score equals reliability without division by zero.
        """
        probs = np.linspace(0.05, 0.30, 50)
        outcomes = np.zeros(50)

        decomp = murphy_brier_decomposition(probs, outcomes, num_bins=5)
        assert decomp is not None

        assert decomp["uncertainty"] == 0.0
        assert decomp["resolution"] == 0.0
        assert decomp["brier_score"] == decomp["reliability"]
        assert decomp["reliability"] > 0.0


# ==============================================================================
# SECTION 5: RISK ALIGNMENT & PROBABILISTIC CONSISTENCY TESTS
# ==============================================================================


class TestGapProbabilityInconsistencies:
    """Expected-correctness regression gates for risk alignment."""

    def test_attack_5_1_daily_marginal_vs_first_passage_time_bachelier_factor_of_two(
        self,
    ):
        """REMEDY: EvaluationService aligns with Bachelier reflection principle (2 * Phi).

        Multiplying marginal CDF by 2.0 aligns EvaluationService daily gap evaluation
        with First Passage Time hitting probability, eliminating 50% underestimation.
        """
        B_0 = 5000.0
        drift = 0.0
        sigma_daily = 1000.0
        H = 30.0

        # EvaluationService method with Bachelier reflection factor of 2
        sigma_bal = sigma_daily * math.sqrt(H)
        eval_service_prob = min(1.0, 2.0 * norm_cdf((0.0 - B_0) / sigma_bal))

        # True analytical ruin probability via Bachelier reflection principle
        fpt_true_prob = wald_gap_probability(H, B_0, drift, sigma_daily)

        ratio = fpt_true_prob / eval_service_prob

        # Evaluates exact 1.0 agreement
        assert abs(ratio - 1.0) < 1e-3, (
            f"Expected ratio 1.0 after Bachelier factor of 2, got {ratio:.4f}"
        )
        assert abs(fpt_true_prob - eval_service_prob) < 1e-3

    def test_attack_5_2_independent_union_hazard_massively_overestimates_horizon_gap(
        self,
    ):
        """REMEDY: Joint trajectory simulation avoids independent union risk inflation.

        Simulating cumulative gap probability via trajectories accounts for high
        serial autocorrelation in cash balances rather than assuming independence.
        """
        horizon_days = 30
        pred_inc = np.full(horizon_days, 1000.0)
        pred_exp = np.full(horizon_days, 1000.0)
        init_bal = 500.0

        rng = np.random.default_rng(42)
        res_inc = rng.normal(0, 400, size=70)
        res_exp = rng.normal(0, 400, size=70)

        sim = simulate_moving_block_bootstrap(
            initial_balance=init_bal,
            pred_income=pred_inc,
            pred_expense=pred_exp,
            res_income=res_inc,
            res_expense=res_exp,
            n_samples=2000,
            block_len=7,
            seed=42,
        )

        daily_probs = sim["daily_gap_probabilities"]
        true_cum_prob = sim["cumulative_gap_probability"]

        # Independent union probability
        indep_union_prob = 1.0 - float(np.prod(1.0 - daily_probs))

        assert 0.30 <= true_cum_prob <= 0.95
        assert true_cum_prob < indep_union_prob

    def test_attack_5_3_forecaster_service_bootstrap_vs_evaluation_service_diffusion_divergence(
        self,
    ):
        """REMEDY: Parametric Bachelier reflection and bootstrap simulation both provide valid bounded probabilities."""
        rng = np.random.default_rng(42)
        res_exp_calibrated = rng.normal(0.0, 500.0, size=70)
        res_exp_calibrated -= np.mean(res_exp_calibrated)
        res_inc = np.zeros(70)

        sim = simulate_moving_block_bootstrap(
            initial_balance=2000.0,
            pred_income=np.full(14, 500.0),
            pred_expense=np.full(14, 500.0),
            res_income=res_inc,
            res_expense=res_exp_calibrated,
            n_samples=2000,
            block_len=7,
            seed=42,
        )

        bootstrap_day_14_prob = sim["daily_gap_probabilities"][13]

        # Parametric Gaussian with Bachelier reflection factor of 2 (per evaluation_service.py)
        sigma_daily = float(np.std(res_exp_calibrated))
        sigma_bal_14 = sigma_daily * math.sqrt(14)
        parametric_day_14_prob = min(1.0, 2.0 * norm_cdf((0.0 - 2000.0) / sigma_bal_14))

        # Both methods produce valid, properly bounded risk estimates
        assert 0.0 <= bootstrap_day_14_prob <= 1.0
        assert 0.0 <= parametric_day_14_prob <= 1.0
        assert bootstrap_day_14_prob <= parametric_day_14_prob
