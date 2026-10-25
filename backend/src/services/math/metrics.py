import numpy as np
from typing import Optional, TypedDict


class MurphyDecomposition(TypedDict):
    brier_score: float
    reliability: float
    resolution: float
    uncertainty: float
    within_bin_variance: float


def compute_wape(actual: np.ndarray, predicted: np.ndarray) -> Optional[float]:
    """
    Computes Weighted Absolute Percentage Error (WAPE).
    WAPE = sum(|actual - predicted|) / sum(|actual|)

    Properties:
    - Scale invariant under positive linear scaling.
    - Defined and stable when individual daily observations are 0,
      provided the aggregate turnover sum(|actual|) > 0.
    - Returns 0.0 when both actual and predicted sum to 0.0 (flawless zero-flow forecast).
    - Returns 1.0 when actual turnover is 0.0 but predicted flow has error.
    - Stabilizes scale on near-zero kopeck turnover (< 1.0 ruble) to prevent unbounded distortion.
    """
    act = np.asarray(actual, dtype=np.float64)
    pred = np.asarray(predicted, dtype=np.float64)
    if act.shape != pred.shape:
        raise ValueError(f"Shape mismatch: actual {act.shape} vs predicted {pred.shape}")
    if np.any(np.isnan(act)) or np.any(np.isnan(pred)):
        raise ValueError("Input arrays contain NaN values")

    total_actual = float(np.sum(np.abs(act)))
    total_abs_err = float(np.sum(np.abs(act - pred)))

    if total_actual <= 0.0:
        if total_abs_err == 0.0:
            return 0.0
        return 1.0

    denom = max(total_actual, 1.0) if total_actual < 1.0 else total_actual
    return round(total_abs_err / denom, 4)


def compute_brier_score(
    probabilities: np.ndarray, binary_outcomes: np.ndarray
) -> Optional[float]:
    """
    Computes Brier Score for probabilistic gap prediction.
    BS = (1/N) * sum((p_i - o_i)^2)

    Strictly proper scoring rule for binary events (o_i in {0, 1}).
    """
    probs = np.asarray(probabilities, dtype=np.float64)
    outcomes = np.asarray(binary_outcomes, dtype=np.float64)
    if probs.shape != outcomes.shape:
        raise ValueError(
            f"Shape mismatch: probabilities {probs.shape} vs outcomes {outcomes.shape}"
        )
    if len(probs) == 0:
        return None

    # Clip probabilities to [0, 1] to ensure numerical stability
    probs_clipped = np.clip(probs, 0.0, 1.0)
    score = float(np.mean((probs_clipped - outcomes) ** 2))
    return round(score, 4)


def murphy_brier_decomposition(
    probabilities: np.ndarray, binary_outcomes: np.ndarray, num_bins: int = 10
) -> Optional[MurphyDecomposition]:
    """
    Decomposes Brier Score into Reliability, Resolution, Uncertainty, and Within-Bin Variance:
    BS_binned = Reliability - Resolution + Uncertainty (Murphy 1973).
    BS_continuous = BS_binned + Within_Bin_Variance.

    - Reliability: calibration error (lower is better, ideally 0.0).
    - Resolution: discriminatory power relative to climatological frequency (higher is better).
    - Uncertainty: base-rate variance = o_bar * (1 - o_bar).
    - Within-Bin Variance: variance of predicted probabilities within discrete bins.
    """
    probs = np.asarray(probabilities, dtype=np.float64)
    outcomes = np.asarray(binary_outcomes, dtype=np.float64)
    n = len(probs)
    if n == 0:
        return None

    probs_clipped = np.clip(probs, 0.0, 1.0)
    base_rate = float(np.mean(outcomes))
    uncertainty = base_rate * (1.0 - base_rate)

    bin_edges = np.linspace(0.0, 1.0, num_bins + 1)
    bin_indices = np.digitize(probs_clipped, bin_edges, right=True)
    # Ensure bin indices in range [1, num_bins]
    bin_indices = np.clip(bin_indices, 1, num_bins)

    reliability = 0.0
    resolution = 0.0
    within_bin_var = 0.0

    for b in range(1, num_bins + 1):
        mask = bin_indices == b
        n_k = int(np.sum(mask))
        if n_k > 0:
            mean_prob_k = float(np.mean(probs_clipped[mask]))
            mean_obs_k = float(np.mean(outcomes[mask]))
            weight = n_k / n
            reliability += weight * ((mean_prob_k - mean_obs_k) ** 2)
            resolution += weight * ((mean_obs_k - base_rate) ** 2)
            within_bin_var += weight * float(np.mean((probs_clipped[mask] - mean_prob_k) ** 2))

    bs_binned = reliability - resolution + uncertainty
    return {
        "brier_score": round(bs_binned, 4),
        "reliability": round(reliability, 4),
        "resolution": round(resolution, 4),
        "uncertainty": round(uncertainty, 4),
        "within_bin_variance": round(within_bin_var, 4),
    }
