#!/usr/bin/env python3
"""
trust-decay-fitter.py — Fit trust decay curves to attestation data.

Compares linear vs exponential vs hyperbolic decay models for trust
freshness scoring. Based on Ebbinghaus forgetting curves applied to
agent attestation validity.

Models:
  - Linear:      score(t) = max(0, 1 - t/T)
  - Exponential: score(t) = exp(-λt), where λ = ln(2)/half_life
  - Hyperbolic:  score(t) = 1 / (1 + kt)

Usage:
  python3 tools/trust-decay-fitter.py                    # demo with synthetic data
  python3 tools/trust-decay-fitter.py --data scores.csv  # fit real data (cols: age_hours,score)

Output: RMSE + R² for each model, recommended half-lives by attestation type.
"""

import csv
import math
import sys
from dataclasses import dataclass


@dataclass
class FitResult:
    model: str
    rmse: float
    r_squared: float
    params: dict


def linear_decay(t: float, T: float) -> float:
    return max(0.0, 1.0 - t / T)


def exponential_decay(t: float, half_life: float) -> float:
    lam = math.log(2) / half_life
    return math.exp(-lam * t)


def hyperbolic_decay(t: float, k: float) -> float:
    return 1.0 / (1.0 + k * t)


def rmse(predicted: list[float], actual: list[float]) -> float:
    n = len(predicted)
    if n == 0:
        return float("inf")
    return math.sqrt(sum((p - a) ** 2 for p, a in zip(predicted, actual)) / n)


def r_squared(predicted: list[float], actual: list[float]) -> float:
    n = len(actual)
    if n == 0:
        return 0.0
    mean_a = sum(actual) / n
    ss_res = sum((a - p) ** 2 for a, p in zip(actual, predicted))
    ss_tot = sum((a - mean_a) ** 2 for a in actual)
    if ss_tot == 0:
        return 1.0 if ss_res == 0 else 0.0
    return 1.0 - ss_res / ss_tot


def grid_search(ages: list[float], scores: list[float], model_fn, param_name: str,
                param_range: list[float]) -> FitResult:
    """Find best parameter by grid search (simple, no scipy needed)."""
    best_rmse = float("inf")
    best_param = param_range[0]
    best_preds = []

    for p in param_range:
        preds = [model_fn(t, p) for t in ages]
        r = rmse(preds, scores)
        if r < best_rmse:
            best_rmse = r
            best_param = p
            best_preds = preds

    return FitResult(
        model=model_fn.__name__,
        rmse=best_rmse,
        r_squared=r_squared(best_preds, scores),
        params={param_name: round(best_param, 3)},
    )


def generate_synthetic_data(n: int = 50, half_life: float = 8.0, noise: float = 0.08) -> tuple:
    """Generate synthetic attestation decay data with exponential + noise."""
    import random
    random.seed(42)
    ages = sorted([random.uniform(0, 48) for _ in range(n)])
    lam = math.log(2) / half_life
    scores = [max(0, min(1, math.exp(-lam * t) + random.gauss(0, noise))) for t in ages]
    return ages, scores


def load_csv(path: str) -> tuple:
    ages, scores = [], []
    with open(path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            ages.append(float(row["age_hours"]))
            scores.append(float(row["score"]))
    return ages, scores


# Domain-specific recommended half-lives (hours)
RECOMMENDED_HALF_LIVES = {
    "runtime_attestation": 4,
    "identity_binding": 720,      # 30 days
    "platform_reputation": 2160,  # 90 days
    "skill_certification": 168,   # 7 days
    "heartbeat_liveness": 1,      # 1 hour
}


def main():
    data_path = None
    for i, arg in enumerate(sys.argv[1:], 1):
        if arg == "--data" and i < len(sys.argv) - 1:
            data_path = sys.argv[i + 1]

    if data_path:
        print(f"Loading data from {data_path}...")
        ages, scores = load_csv(data_path)
    else:
        print("Using synthetic data (exponential decay, t½=8h, noise=0.08)")
        ages, scores = generate_synthetic_data()

    print(f"Data points: {len(ages)}")
    print(f"Age range: {min(ages):.1f}h — {max(ages):.1f}h")
    print(f"Score range: {min(scores):.3f} — {max(scores):.3f}")
    print()

    # Parameter search ranges
    linear_range = [i * 0.5 for i in range(2, 200)]  # T: 1-100h
    exp_range = [i * 0.25 for i in range(1, 400)]     # half_life: 0.25-100h
    hyp_range = [i * 0.01 for i in range(1, 500)]     # k: 0.01-5.0

    results = [
        grid_search(ages, scores, linear_decay, "T", linear_range),
        grid_search(ages, scores, exponential_decay, "half_life", exp_range),
        grid_search(ages, scores, hyperbolic_decay, "k", hyp_range),
    ]

    print("=" * 60)
    print("Model Comparison")
    print("=" * 60)
    print(f"{'Model':<20} {'RMSE':>8} {'R²':>8}  Params")
    print("-" * 60)
    for r in sorted(results, key=lambda x: x.rmse):
        params_str = ", ".join(f"{k}={v}" for k, v in r.params.items())
        print(f"{r.model:<20} {r.rmse:>8.4f} {r.r_squared:>8.4f}  {params_str}")

    best = min(results, key=lambda x: x.rmse)
    print(f"\nBest fit: {best.model} (RMSE={best.rmse:.4f}, R²={best.r_squared:.4f})")

    print("\n" + "=" * 60)
    print("Recommended Half-Lives by Attestation Type")
    print("=" * 60)
    for atype, hl in RECOMMENDED_HALF_LIVES.items():
        if hl >= 24:
            display = f"{hl/24:.0f}d"
        else:
            display = f"{hl}h"
        print(f"  {atype:<25} t½ = {display}")

    print(f"\nGrade: {'A' if best.r_squared > 0.9 else 'B' if best.r_squared > 0.7 else 'C'}")


if __name__ == "__main__":
    main()
