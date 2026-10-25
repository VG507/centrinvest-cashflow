import numpy as np
from typing import TypedDict, Optional


class ConformalCalibrationResult(TypedDict):
    calibrated_lower: np.ndarray
    calibrated_upper: np.ndarray
    conformal_shift: float
    nominal_coverage: float
    historical_coverage: float
    sample_size: int


def compute_empirical_coverage(
    actual: np.ndarray, lower_bounds: np.ndarray, upper_bounds: np.ndarray
) -> float:
    """
    Computes empirical coverage: proportion of actual values within [lower_bounds, upper_bounds].
    """
    act = np.asarray(actual, dtype=np.float64)
    low = np.asarray(lower_bounds, dtype=np.float64)
    upp = np.asarray(upper_bounds, dtype=np.float64)

    if not (len(act) == len(low) == len(upp)):
        raise ValueError("Array length mismatch in empirical coverage computation")
    if len(act) == 0:
        return 0.0

    in_bounds = (act >= low) & (act <= upp)
    return round(float(np.mean(in_bounds)), 4)


def calibrate_conformal_corridor(
    predicted_lower: np.ndarray,
    predicted_upper: np.ndarray,
    historical_actual: np.ndarray,
    historical_lower: np.ndarray,
    historical_upper: np.ndarray,
    alpha: float = 0.20,
    point_predictions: Optional[np.ndarray] = None,
) -> ConformalCalibrationResult:
    """
    Calibrates prediction intervals using Split Conformal Risk Control / EnbPI
    to provide finite-sample coverage guarantees without parametric Gaussian assumptions.

    Non-conformity score:
    S_t = max(historical_lower_t - actual_t, actual_t - historical_upper_t)

    Positive S_t means the actual observation fell outside the corridor.
    The (1 - alpha)(1 + 1/N) quantile of S_t determines the conformal adjustment shift k.
    """
    h_act = np.asarray(historical_actual, dtype=np.float64)
    h_low = np.asarray(historical_lower, dtype=np.float64)
    h_upp = np.asarray(historical_upper, dtype=np.float64)

    p_low = np.asarray(predicted_lower, dtype=np.float64)
    p_upp = np.asarray(predicted_upper, dtype=np.float64)

    if point_predictions is not None:
        point_pred = np.asarray(point_predictions, dtype=np.float64)
    else:
        point_pred = (p_low + p_upp) / 2.0

    n = len(h_act)
    scale_floor = 0.01 * np.abs(point_pred)
    base_min_width = np.maximum(np.maximum(0.5 * (p_upp - p_low), 10.0), scale_floor)

    if n < 5:
        # Insufficient historical validation points: return unadjusted bounds
        cal_low = np.minimum(p_low, point_pred)
        cal_upp = np.maximum(p_upp, point_pred)
        current_width = cal_upp - cal_low
        narrow_mask = current_width < base_min_width
        if np.any(narrow_mask):
            deficit = base_min_width - current_width
            cal_low = np.where(narrow_mask, cal_low - deficit / 2.0, cal_low)
            cal_upp = np.where(narrow_mask, cal_upp + deficit / 2.0, cal_upp)
        cal_low = np.floor(np.round(cal_low, 3) * 100.0) / 100.0
        cal_upp = np.ceil(np.round(cal_upp, 3) * 100.0) / 100.0
        cal_low = np.minimum(cal_low, np.floor(point_pred * 100.0) / 100.0)
        cal_upp = np.maximum(cal_upp, np.ceil(point_pred * 100.0) / 100.0)
        cal_upp = np.maximum(cal_upp, cal_low)
        hist_cov = compute_empirical_coverage(h_act, h_low, h_upp) if len(h_act) > 0 else 0.0
        return {
            "calibrated_lower": cal_low,
            "calibrated_upper": cal_upp,
            "conformal_shift": 0.0,
            "nominal_coverage": 1.0 - alpha,
            "historical_coverage": hist_cov,
            "sample_size": n,
        }

    # Non-conformity scores bounded below by 0.0 to prevent quiet-period interval contraction
    scores = np.maximum(0.0, np.maximum(h_low - h_act, h_act - h_upp))

    # Finite sample adjusted quantile level: (1 - alpha) * (1 + 1/N)
    quantile_level = min(1.0, (1.0 - alpha) * (1.0 + (1.0 / float(n))))
    conformal_shift = max(0.0, float(np.quantile(scores, quantile_level)))

    # Apply shift to predicted corridor
    cal_low = p_low - conformal_shift
    cal_upp = p_upp + conformal_shift

    # Confidence interval invariants:
    # 1) Lower and upper bounds must enclose the point prediction: L_t <= pred_t <= U_t
    # 2) Corridor width U_t - L_t must be strictly positive and scale-relative
    cal_low = np.minimum(cal_low, point_pred)
    cal_upp = np.maximum(cal_upp, point_pred)

    min_width = base_min_width
    current_width = cal_upp - cal_low
    narrow_mask = current_width < min_width
    if np.any(narrow_mask):
        deficit = min_width - current_width
        cal_low = np.where(narrow_mask, cal_low - deficit / 2.0, cal_low)
        cal_upp = np.where(narrow_mask, cal_upp + deficit / 2.0, cal_upp)

    # Floor cal_low and ceil cal_upp at cent resolution so rounding never shrinks bounds or breaches point_pred
    cal_low = np.floor(np.round(cal_low, 3) * 100.0) / 100.0
    cal_upp = np.ceil(np.round(cal_upp, 3) * 100.0) / 100.0
    cal_low = np.minimum(cal_low, np.floor(point_pred * 100.0) / 100.0)
    cal_upp = np.maximum(cal_upp, np.ceil(point_pred * 100.0) / 100.0)
    cal_upp = np.maximum(cal_upp, cal_low)

    # Historical coverage before calibration
    hist_cov = compute_empirical_coverage(h_act, h_low, h_upp)

    return {
        "calibrated_lower": cal_low,
        "calibrated_upper": cal_upp,
        "conformal_shift": round(conformal_shift, 2),
        "nominal_coverage": round(1.0 - alpha, 4),
        "historical_coverage": hist_cov,
        "sample_size": n,
    }


def adaptive_conformal_step(
    current_lower: float,
    current_upper: float,
    actual: float,
    alpha_t: float,
    target_alpha: float = 0.20,
    gamma: float = 0.05,
) -> tuple[float, float, float]:
    """
    Adaptive Conformal Inference (ACI) step (Gibbs & Candes 2021).
    Adjusts nominal non-coverage rate alpha_t sequentially and adapts
    the prediction corridor under out-of-distribution regime shifts.
    """
    is_covered = (actual >= current_lower) and (actual <= current_upper)
    err_t = 0.0 if is_covered else 1.0
    alpha_next = max(0.01, min(0.99, alpha_t + gamma * (target_alpha - err_t)))
    width = current_upper - current_lower
    if not is_covered:
        if actual < current_lower:
            new_lower = current_lower - max(current_lower - actual + 10.0, 0.25 * width)
            new_upper = current_upper
        else:
            new_lower = current_lower
            new_upper = current_upper + max(actual - current_upper + 10.0, 0.25 * width)
    else:
        new_lower = current_lower
        new_upper = current_upper

    return float(new_lower), float(new_upper), float(alpha_next)

