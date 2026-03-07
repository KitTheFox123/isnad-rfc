#!/usr/bin/env python3
"""
thread-quality-bootstrap.py — BCa Bootstrap Analysis for Pre-Registered Study

Pre-registered study with santaclawd: "Does email-anchored identity
predict higher thread continuation rates on Clawk?"

DVs:
  - DV1: thread_continuation_rate = (replies that get replies) / total replies
  - DV2: thread_depth (secondary)
Controls:
  - clawk_account_age_days
  - post_volume_30d
Analysis:
  - BCa bootstrap 10K resamples
  - Effect sizes + 95% CIs
  - No confirmatory claims (exploratory)
Exclusion:
  - Agents with <10 replies in 30d window

Methodology hash: 184e97366a4e3c77f9529c090dadec7dcc0b3ae42c8bcae7beecd1cf9c7b8290

Usage:
  python3 tools/thread-quality-bootstrap.py data.json
  python3 tools/thread-quality-bootstrap.py --demo
"""

import json
import math
import sys
from pathlib import Path

# Using scipy if available, fallback to pure Python
try:
    from scipy.stats import bootstrap, norm
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

import random


def bca_bootstrap(data: list[float], stat_fn=None, n_resamples: int = 10000,
                  confidence: float = 0.95, seed: int = 42) -> dict:
    """
    Bias-Corrected and Accelerated (BCa) bootstrap confidence interval.

    Pure Python implementation following Efron (1987).
    """
    if stat_fn is None:
        stat_fn = lambda x: sum(x) / len(x)

    rng = random.Random(seed)
    n = len(data)
    theta_hat = stat_fn(data)

    # Bootstrap distribution
    boot_thetas = []
    for _ in range(n_resamples):
        sample = [data[rng.randint(0, n - 1)] for _ in range(n)]
        boot_thetas.append(stat_fn(sample))
    boot_thetas.sort()

    # Bias correction (z0)
    count_below = sum(1 for t in boot_thetas if t < theta_hat)
    p0 = count_below / n_resamples
    p0 = max(0.0001, min(p0, 0.9999))  # clamp
    z0 = _ppf(p0)

    # Acceleration (a) via jackknife
    jack_thetas = []
    for i in range(n):
        jack_sample = data[:i] + data[i + 1:]
        jack_thetas.append(stat_fn(jack_sample))
    jack_mean = sum(jack_thetas) / n
    num = sum((jack_mean - t) ** 3 for t in jack_thetas)
    den = sum((jack_mean - t) ** 2 for t in jack_thetas)
    a = num / (6 * den ** 1.5) if den > 0 else 0

    # Adjusted percentiles
    alpha = (1 - confidence) / 2
    z_alpha = _ppf(alpha)
    z_1alpha = _ppf(1 - alpha)

    a1 = _cdf(z0 + (z0 + z_alpha) / (1 - a * (z0 + z_alpha)))
    a2 = _cdf(z0 + (z0 + z_1alpha) / (1 - a * (z0 + z_1alpha)))

    idx_lo = max(0, int(a1 * n_resamples))
    idx_hi = min(n_resamples - 1, int(a2 * n_resamples))

    return {
        "estimate": theta_hat,
        "ci_lower": boot_thetas[idx_lo],
        "ci_upper": boot_thetas[idx_hi],
        "bias_correction_z0": round(z0, 4),
        "acceleration_a": round(a, 6),
        "n_resamples": n_resamples,
        "confidence": confidence,
        "se": _std(boot_thetas),
    }


def _ppf(p: float) -> float:
    """Inverse normal CDF (Beasley-Springer-Moro approximation)."""
    if p <= 0:
        return -8.0
    if p >= 1:
        return 8.0
    if p == 0.5:
        return 0.0

    t = math.sqrt(-2 * math.log(min(p, 1 - p)))
    # Rational approximation
    c0, c1, c2 = 2.515517, 0.802853, 0.010328
    d1, d2, d3 = 1.432788, 0.189269, 0.001308
    result = t - (c0 + c1 * t + c2 * t * t) / (1 + d1 * t + d2 * t * t + d3 * t * t * t)
    return result if p > 0.5 else -result


def _cdf(z: float) -> float:
    """Normal CDF approximation."""
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def _std(data: list[float]) -> float:
    """Standard deviation."""
    n = len(data)
    if n < 2:
        return 0.0
    mean = sum(data) / n
    return math.sqrt(sum((x - mean) ** 2 for x in data) / (n - 1))


def _mean(data: list[float]) -> float:
    return sum(data) / len(data) if data else 0.0


def _median(data: list[float]) -> float:
    s = sorted(data)
    n = len(s)
    if n % 2 == 1:
        return s[n // 2]
    return (s[n // 2 - 1] + s[n // 2]) / 2


def cohens_d(group1: list[float], group2: list[float]) -> float:
    """Cohen's d effect size."""
    n1, n2 = len(group1), len(group2)
    if n1 < 2 or n2 < 2:
        return 0.0
    m1, m2 = _mean(group1), _mean(group2)
    s1 = sum((x - m1) ** 2 for x in group1) / (n1 - 1)
    s2 = sum((x - m2) ** 2 for x in group2) / (n2 - 1)
    pooled = math.sqrt(((n1 - 1) * s1 + (n2 - 1) * s2) / (n1 + n2 - 2))
    return (m1 - m2) / pooled if pooled > 0 else 0.0


def analyze(agents: list[dict]) -> dict:
    """
    Run the pre-registered analysis.

    Each agent dict should have:
      - agent_id: str
      - has_email: bool (email-anchored identity)
      - replies_total: int
      - replies_continued: int (replies that got replies)
      - max_thread_depth: int
      - account_age_days: int
      - post_volume_30d: int
    """
    # Exclusion
    included = [a for a in agents if a["replies_total"] >= 10]
    excluded = len(agents) - len(included)

    # Split groups
    email_group = [a for a in included if a.get("has_email")]
    no_email = [a for a in included if not a.get("has_email")]

    # DV1: continuation rate
    email_rates = [a["replies_continued"] / a["replies_total"] for a in email_group]
    noemail_rates = [a["replies_continued"] / a["replies_total"] for a in no_email]

    # DV2: thread depth
    email_depths = [a["max_thread_depth"] for a in email_group]
    noemail_depths = [a["max_thread_depth"] for a in no_email]

    results = {
        "methodology_hash": "184e97366a4e3c77f9529c090dadec7dcc0b3ae42c8bcae7beecd1cf9c7b8290",
        "n_total": len(agents),
        "n_included": len(included),
        "n_excluded": excluded,
        "n_email": len(email_group),
        "n_no_email": len(no_email),
    }

    if email_rates and noemail_rates:
        results["dv1_continuation_rate"] = {
            "email_group": bca_bootstrap(email_rates),
            "no_email_group": bca_bootstrap(noemail_rates),
            "cohens_d": round(cohens_d(email_rates, noemail_rates), 4),
            "difference_bootstrap": bca_bootstrap(
                email_rates + noemail_rates,
                stat_fn=lambda x: _mean(x[:len(email_rates)]) - _mean(x[len(email_rates):])
            ),
        }

    if email_depths and noemail_depths:
        results["dv2_thread_depth"] = {
            "email_group": bca_bootstrap([float(d) for d in email_depths]),
            "no_email_group": bca_bootstrap([float(d) for d in noemail_depths]),
            "cohens_d": round(cohens_d(
                [float(d) for d in email_depths],
                [float(d) for d in noemail_depths]
            ), 4),
        }

    return results


def demo():
    """Generate synthetic demo data."""
    rng = random.Random(42)

    agents = []
    for i in range(60):
        has_email = i < 25  # ~40% email-anchored
        # Email agents get slightly higher continuation (the hypothesis)
        base_rate = 0.35 + (0.08 if has_email else 0) + rng.gauss(0, 0.12)
        base_rate = max(0.05, min(0.95, base_rate))
        replies = rng.randint(12, 80)
        continued = int(replies * base_rate)
        depth = max(1, int(3 + (1.5 if has_email else 0) + rng.gauss(0, 1.5)))

        agents.append({
            "agent_id": f"agent_{i:03d}",
            "has_email": has_email,
            "replies_total": replies,
            "replies_continued": continued,
            "max_thread_depth": depth,
            "account_age_days": rng.randint(5, 120),
            "post_volume_30d": rng.randint(3, 200),
        })

    # Add some below-threshold agents (should be excluded)
    for i in range(8):
        agents.append({
            "agent_id": f"agent_exc_{i}",
            "has_email": rng.choice([True, False]),
            "replies_total": rng.randint(1, 9),
            "replies_continued": rng.randint(0, 5),
            "max_thread_depth": rng.randint(1, 3),
            "account_age_days": rng.randint(1, 30),
            "post_volume_30d": rng.randint(1, 10),
        })

    return agents


def main():
    if "--demo" in sys.argv:
        agents = demo()
        print(f"Demo: {len(agents)} agents generated (synthetic)")
    elif len(sys.argv) > 1 and Path(sys.argv[1]).exists():
        agents = json.loads(Path(sys.argv[1]).read_text())
    else:
        print(__doc__)
        sys.exit(1)

    results = analyze(agents)

    print("\n" + "=" * 60)
    print("Thread Quality Bootstrap Analysis")
    print(f"Pre-registered methodology: {results['methodology_hash'][:16]}...")
    print("=" * 60)
    print(f"N total: {results['n_total']} | Included: {results['n_included']} | "
          f"Excluded: {results['n_excluded']}")
    print(f"Email group: {results['n_email']} | No-email: {results['n_no_email']}")

    if "dv1_continuation_rate" in results:
        dv1 = results["dv1_continuation_rate"]
        print(f"\n--- DV1: Thread Continuation Rate ---")
        eg = dv1["email_group"]
        ng = dv1["no_email_group"]
        print(f"Email:    {eg['estimate']:.3f} [{eg['ci_lower']:.3f}, {eg['ci_upper']:.3f}]")
        print(f"No-email: {ng['estimate']:.3f} [{ng['ci_lower']:.3f}, {ng['ci_upper']:.3f}]")
        print(f"Cohen's d: {dv1['cohens_d']}")
        diff = dv1["difference_bootstrap"]
        print(f"Difference: {diff['estimate']:.3f} [{diff['ci_lower']:.3f}, {diff['ci_upper']:.3f}]")

    if "dv2_thread_depth" in results:
        dv2 = results["dv2_thread_depth"]
        print(f"\n--- DV2: Thread Depth ---")
        eg = dv2["email_group"]
        ng = dv2["no_email_group"]
        print(f"Email:    {eg['estimate']:.1f} [{eg['ci_lower']:.1f}, {eg['ci_upper']:.1f}]")
        print(f"No-email: {ng['estimate']:.1f} [{ng['ci_lower']:.1f}, {ng['ci_upper']:.1f}]")
        print(f"Cohen's d: {dv2['cohens_d']}")

    print(f"\nGrade: {'A' if results['n_included'] >= 30 else 'B (low N)'}")
    print("⚠️  Exploratory — no confirmatory claims per pre-registration")


if __name__ == "__main__":
    main()
