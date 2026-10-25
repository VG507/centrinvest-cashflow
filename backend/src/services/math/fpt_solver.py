import math
import numpy as np
from typing import TypedDict, Optional


class FPTAnalyticalResult(TypedDict):
    ruin_probability: float
    modal_ruin_time: Optional[float]
    instantaneous_hazard_horizon: float


class BootstrapSimulationResult(TypedDict):
    trajectories: np.ndarray
    lower_bounds: np.ndarray
    upper_bounds: np.ndarray
    daily_gap_probabilities: np.ndarray
    cumulative_gap_probability: float


def norm_cdf(z: float) -> float:
    """Standard normal cumulative distribution function."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def wald_fpt_density(
    t: float, initial_balance: float, drift: float, sigma: float
) -> float:
    """
    Computes the probability density function of First-Passage Time to zero barrier
    under Brownian motion with drift:
    B_t = B_0 + drift * t + sigma * W_t, with absorbing barrier at 0 (B_0 > 0).

    Density f_T(t) corresponds to the Wald (Inverse Gaussian) distribution:
    f_T(t) = (B_0 / (sigma * sqrt(2 * pi * t^3))) * exp( - (B_0 + drift * t)^2 / (2 * sigma^2 * t) )
    """
    if t <= 0.0 or initial_balance <= 0.0 or sigma <= 0.0:
        return 0.0

    coef = initial_balance / (sigma * math.sqrt(2.0 * math.pi * (t**3)))
    exponent = -((initial_balance + drift * t) ** 2) / (2.0 * (sigma**2) * t)
    # Numerical guard against underflow
    if exponent < -500.0:
        return 0.0
    return coef * math.exp(exponent)


def wald_gap_probability(
    horizon: float, initial_balance: float, drift: float, sigma: float
) -> float:
    """
    Calculates the cumulative ruin probability within horizon H:
    P(T <= H) = Phi((-drift * H - B_0) / (sigma * sqrt(H)))
                + exp(-2 * drift * B_0 / sigma^2) * Phi((drift * H - B_0) / (sigma * sqrt(H)))

    Derivation via Bachelier reflection principle and Girsanov change of measure.
    """
    if initial_balance <= 0.0:
        return 1.0
    if horizon <= 0.0 or sigma <= 0.0:
        return 0.0

    sqrt_h = math.sqrt(horizon)
    z1 = (-drift * horizon - initial_balance) / (sigma * sqrt_h)
    z2 = (drift * horizon - initial_balance) / (sigma * sqrt_h)
    term1 = norm_cdf(z1)

    exp_arg = -2.0 * drift * initial_balance / (sigma**2)
    if z2 < -30.0:
        # Asymptotic cancellation: exp(exp_arg) * phi(z2) == phi(z1)
        # Via Mill's ratio: exp(exp_arg) * Phi(z2) ~ (phi(z1) / -z2) * (1 - 1 / z2^2)
        if z1 > -38.0:
            phi_z1 = (1.0 / math.sqrt(2.0 * math.pi)) * math.exp(-0.5 * (z1**2))
            term2 = (phi_z1 / -z2) * (1.0 - (1.0 / (z2**2)))
        else:
            term2 = 0.0
    elif exp_arg > 700.0:
        log_term2 = exp_arg + math.log(max(norm_cdf(z2), 1e-300))
        term2 = math.exp(log_term2) if log_term2 < 0.0 else 1.0
    elif exp_arg < -700.0:
        term2 = 0.0
    else:
        term2 = math.exp(exp_arg) * norm_cdf(z2)

    total_prob = term1 + term2
    return max(0.0, min(1.0, float(total_prob)))


def compute_analytical_fpt(
    initial_balance: float, drift: float, sigma: float, horizon_days: int
) -> FPTAnalyticalResult:
    """
    Computes analytical ruin probability, mode of the ruin time distribution,
    and hazard rate at the end of the horizon.
    """
    ruin_prob = wald_gap_probability(float(horizon_days), initial_balance, drift, sigma)

    # Mode of Inverse Gaussian distribution
    # Rationalized formula: 2 * lambda / (sqrt(4 * gamma^2 + 9) + 3)
    # Eliminates float64 catastrophic cancellation to 0.0 and ZeroDivisionError
    modal_time = None
    if drift < 0.0 and initial_balance > 0.0 and sigma > 0.0:
        mu_param = -initial_balance / drift
        lambda_param = (initial_balance**2) / (sigma**2)
        gamma = lambda_param / mu_param if mu_param > 0.0 else 0.0
        if gamma <= 1e-8:
            modal_time = (lambda_param / 3.0) * (1.0 - (1.0 / 9.0) * (gamma**2))
        else:
            modal_time = (2.0 * lambda_param) / (math.sqrt(4.0 * (gamma**2) + 9.0) + 3.0)

    density_h = wald_fpt_density(float(horizon_days), initial_balance, drift, sigma)
    survival_h = max(1.0 - ruin_prob, 1e-6)
    hazard_h = density_h / survival_h

    return {
        "ruin_probability": round(ruin_prob, 4),
        "modal_ruin_time": round(modal_time, 2) if modal_time is not None else None,
        "instantaneous_hazard_horizon": round(hazard_h, 6),
    }


def simulate_moving_block_bootstrap(
    initial_balance: float,
    pred_income: np.ndarray,
    pred_expense: np.ndarray,
    res_income: np.ndarray,
    res_expense: np.ndarray,
    n_samples: int = 1000,
    block_len: int = 7,
    seed: int = 42,
    forecast_start_weekday: Optional[int] = None,
    history_start_weekday: Optional[int] = None,
) -> BootstrapSimulationResult:
    """
    Simulates stochastic cashflow trajectories using non-parametric Moving Block Bootstrap (MBB).
    Preserves 7-day cyclical dependencies and autocorrelation without Gaussian assumptions,
    with weekday phase alignment and expectation-preserving non-negative scaling to eliminate
    asymmetric rectifier drift bias.
    """
    horizon_days = len(pred_income)
    n_hist = len(res_income)
    trajectories = np.zeros((n_samples, horizon_days), dtype=np.float64)
    rng = np.random.default_rng(seed)

    if n_hist >= block_len:
        num_blocks = (horizon_days // block_len) + 1
        max_start = n_hist - block_len

        # Weekday phase alignment
        if forecast_start_weekday is not None and history_start_weekday is not None:
            phase = (int(forecast_start_weekday) - int(history_start_weekday)) % block_len
            valid_starts = [st for st in range(0, max_start + 1) if (st % block_len) == phase]
            if not valid_starts:
                valid_starts = list(range(0, max_start + 1))
        elif forecast_start_weekday is not None:
            phase = int(forecast_start_weekday) % block_len
            valid_starts = [st for st in range(0, max_start + 1) if (st % block_len) == phase]
            if not valid_starts:
                valid_starts = list(range(0, max_start + 1))
        else:
            valid_starts = list(range(0, max_start + 1))

        valid_starts_arr = np.array(valid_starts, dtype=np.int64)
        raw_sim_inc = np.zeros((n_samples, horizon_days), dtype=np.float64)
        raw_sim_exp = np.zeros((n_samples, horizon_days), dtype=np.float64)

        for s in range(n_samples):
            starts = rng.choice(valid_starts_arr, size=num_blocks)
            sim_res_inc = np.concatenate([res_income[st : st + block_len] for st in starts])[
                :horizon_days
            ]
            sim_res_exp = np.concatenate([res_expense[st : st + block_len] for st in starts])[
                :horizon_days
            ]
            raw_sim_inc[s, :] = np.maximum(0.0, pred_income + sim_res_inc)
            raw_sim_exp[s, :] = np.maximum(0.0, pred_expense + sim_res_exp)

        # Expectation-preserving scaling across trajectories
        sim_inc = np.zeros((n_samples, horizon_days), dtype=np.float64)
        sim_exp = np.zeros((n_samples, horizon_days), dtype=np.float64)
        for t in range(horizon_days):
            if pred_income[t] == 0.0:
                sim_inc[:, t] = 0.0
            else:
                m_inc = float(np.mean(raw_sim_inc[:, t]))
                sim_inc[:, t] = raw_sim_inc[:, t] * (pred_income[t] / m_inc) if m_inc > 0.0 else pred_income[t]

            if pred_expense[t] == 0.0:
                sim_exp[:, t] = 0.0
            else:
                m_exp = float(np.mean(raw_sim_exp[:, t]))
                sim_exp[:, t] = raw_sim_exp[:, t] * (pred_expense[t] / m_exp) if m_exp > 0.0 else pred_expense[t]

        for s in range(n_samples):
            trajectories[s, :] = initial_balance + np.cumsum(sim_inc[s, :] - sim_exp[s, :])

    elif n_hist > 0:
        w0 = int(forecast_start_weekday) if forecast_start_weekday is not None else 0
        wh0 = int(history_start_weekday) if history_start_weekday is not None else 0
        raw_sim_inc = np.zeros((n_samples, horizon_days), dtype=np.float64)
        raw_sim_exp = np.zeros((n_samples, horizon_days), dtype=np.float64)

        for s in range(n_samples):
            indices = []
            for t in range(horizon_days):
                target_w = (w0 + t) % 7
                matching = [i for i in range(n_hist) if (wh0 + i) % 7 == target_w]
                if matching:
                    indices.append(rng.choice(matching))
                else:
                    is_target_weekend = target_w >= 5
                    cat_matching = [i for i in range(n_hist) if ((wh0 + i) % 7 >= 5) == is_target_weekend]
                    if cat_matching:
                        indices.append(rng.choice(cat_matching))
                    else:
                        indices.append((w0 + t - wh0) % n_hist)

            indices_arr = np.array(indices, dtype=np.int64)
            raw_sim_inc[s, :] = np.maximum(0.0, pred_income + res_income[indices_arr])
            raw_sim_exp[s, :] = np.maximum(0.0, pred_expense + res_expense[indices_arr])

        # Expectation-preserving scaling across trajectories
        sim_inc = np.zeros((n_samples, horizon_days), dtype=np.float64)
        sim_exp = np.zeros((n_samples, horizon_days), dtype=np.float64)
        for t in range(horizon_days):
            if pred_income[t] == 0.0:
                sim_inc[:, t] = 0.0
            else:
                m_inc = float(np.mean(raw_sim_inc[:, t]))
                sim_inc[:, t] = raw_sim_inc[:, t] * (pred_income[t] / m_inc) if m_inc > 0.0 else pred_income[t]

            if pred_expense[t] == 0.0:
                sim_exp[:, t] = 0.0
            else:
                m_exp = float(np.mean(raw_sim_exp[:, t]))
                sim_exp[:, t] = raw_sim_exp[:, t] * (pred_expense[t] / m_exp) if m_exp > 0.0 else pred_expense[t]

        for s in range(n_samples):
            trajectories[s, :] = initial_balance + np.cumsum(sim_inc[s, :] - sim_exp[s, :])
    else:
        # Fallback if no residuals available
        point_bal = initial_balance + np.cumsum(pred_income - pred_expense)
        trajectories = np.tile(point_bal, (n_samples, 1))

    lower_bounds = np.round(np.percentile(trajectories, 10, axis=0), 2)
    upper_bounds = np.round(np.percentile(trajectories, 90, axis=0), 2)
    gap_probs = np.round(np.mean(trajectories < 0.0, axis=0), 4)

    any_gap_sims = np.any(trajectories < 0.0, axis=1)
    cumulative_gap_prob = round(float(np.mean(any_gap_sims)), 4)

    return {
        "trajectories": trajectories,
        "lower_bounds": lower_bounds,
        "upper_bounds": upper_bounds,
        "daily_gap_probabilities": gap_probs,
        "cumulative_gap_probability": cumulative_gap_prob,
    }
