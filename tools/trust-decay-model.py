#!/usr/bin/env python3
"""
trust-decay-model.py — Ebbinghaus-inspired trust decay for attestations

Models trust score decay over time using empirically-validated forgetting
curves (Murre & Dros 2015, replicating Ebbinghaus 1885). Attestations lose
value over time unless renewed — like memories without rehearsal.

Key insight: Linear decay (current isnad default) underweights recent
attestations and overweights old ones. Exponential/power-law decay better
matches how trust actually works:
  - Fresh attestation (< 1h): near-full weight
  - Stale attestation (> 24h): steep dropoff
  - Ancient attestation (> 7d): near-zero without renewal

Three models compared:
  1. Linear decay (baseline)
  2. Exponential decay: R(t) = e^(-t/τ), τ = half-life
  3. Power-law decay: R(t) = (1+t)^(-β), β = decay exponent

Usage:
  python3 tools/trust-decay-model.py [--half-life 4] [--demo]
  python3 tools/trust-decay-model.py --compare  # compare all three models
"""

import argparse
import math
import sys
from dataclasses import dataclass


@dataclass
class Attestation:
    """A trust attestation with timestamp."""
    source: str
    age_hours: float
    raw_score: float  # 0.0-1.0


def linear_decay(age_hours: float, max_age: float = 168.0) -> float:
    """Linear decay over max_age hours. Default: 7 days."""
    return max(0.0, 1.0 - age_hours / max_age)


def exponential_decay(age_hours: float, half_life: float = 4.0) -> float:
    """Exponential decay with configurable half-life (hours).
    
    Ebbinghaus found ~1 hour half-life for nonsense syllables.
    Trust attestations are more meaningful, so default τ = 4h.
    Runtime attestations: τ = 4h (tight coupling).
    Identity attestations: τ = 168h (weekly renewal).
    """
    return math.exp(-0.693 * age_hours / half_life)


def power_law_decay(age_hours: float, beta: float = 0.5) -> float:
    """Power-law decay: R(t) = (1+t)^(-β).
    
    Power-law fits Ebbinghaus data better than exponential for
    longer intervals (Wixted & Ebbesen, 1991). Memory researchers
    debate which model wins; both beat linear.
    """
    return (1.0 + age_hours) ** (-beta)


def weighted_trust_score(
    attestations: list[Attestation],
    decay_fn,
    **kwargs
) -> float:
    """Compute aggregate trust score with time-weighted attestations."""
    if not attestations:
        return 0.0
    
    total_weight = 0.0
    weighted_sum = 0.0
    
    for att in attestations:
        weight = decay_fn(att.age_hours, **kwargs)
        weighted_sum += att.raw_score * weight
        total_weight += weight
    
    if total_weight < 0.001:
        return 0.0
    
    return weighted_sum / total_weight


def grade(score: float) -> str:
    """Letter grade from score."""
    if score >= 0.9: return "A"
    if score >= 0.8: return "B"
    if score >= 0.7: return "C"
    if score >= 0.6: return "D"
    return "F"


def demo():
    """Run demo with sample attestations at various ages."""
    print("=" * 60)
    print("Trust Decay Model — Ebbinghaus-Inspired")
    print("=" * 60)
    
    attestations = [
        Attestation("platform_a", 0.5, 0.95),   # 30 min ago
        Attestation("platform_b", 2.0, 0.90),    # 2 hours ago
        Attestation("counterparty", 8.0, 0.85),  # 8 hours ago
        Attestation("auditor", 24.0, 0.92),      # 1 day ago
        Attestation("old_review", 72.0, 0.88),   # 3 days ago
        Attestation("ancient", 168.0, 0.95),     # 7 days ago
    ]
    
    print("\nAttestations:")
    for a in attestations:
        print(f"  {a.source:15s}  age={a.age_hours:6.1f}h  raw={a.raw_score:.2f}")
    
    print("\nDecay weights by model:")
    print(f"  {'Source':15s}  {'Linear':>8s}  {'Exp(4h)':>8s}  {'Power':>8s}")
    for a in attestations:
        l = linear_decay(a.age_hours)
        e = exponential_decay(a.age_hours, half_life=4.0)
        p = power_law_decay(a.age_hours)
        print(f"  {a.source:15s}  {l:8.3f}  {e:8.3f}  {p:8.3f}")
    
    print("\nAggregate trust scores:")
    for name, fn, kw in [
        ("Linear", linear_decay, {}),
        ("Exponential (τ=4h)", exponential_decay, {"half_life": 4.0}),
        ("Exponential (τ=24h)", exponential_decay, {"half_life": 24.0}),
        ("Power-law (β=0.5)", power_law_decay, {"beta": 0.5}),
    ]:
        score = weighted_trust_score(attestations, fn, **kw)
        print(f"  {name:25s}  score={score:.3f}  grade={grade(score)}")
    
    # Show the key insight
    print("\n" + "-" * 60)
    print("KEY INSIGHT:")
    print("Linear decay gives 0.857 weight to a 24h attestation.")
    print(f"Exponential (τ=4h) gives {exponential_decay(24.0, 4.0):.3f}.")
    print("Which better matches your intuition about 'is this still valid'?")
    print()
    print("Ebbinghaus (1885, replicated Murre & Dros 2015):")
    print("  20 min → 58% retained")
    print("  1 hour → 44% retained")
    print("  9 hours → 36% retained")
    print("  1 day → 33% retained")
    print("  31 days → 21% retained")
    print()
    print("Trust should decay faster than memory — no rehearsal possible")
    print("for a stale attestation. The attestor's state may have changed.")


def compare():
    """Compare models at key time points."""
    print(f"{'Hours':>6s}  {'Linear':>8s}  {'Exp4h':>8s}  {'Exp24h':>8s}  {'Power':>8s}")
    for h in [0, 0.5, 1, 2, 4, 8, 12, 24, 48, 72, 168]:
        l = linear_decay(h)
        e4 = exponential_decay(h, 4.0)
        e24 = exponential_decay(h, 24.0)
        p = power_law_decay(h)
        print(f"{h:6.1f}  {l:8.3f}  {e4:8.3f}  {e24:8.3f}  {p:8.3f}")


def main():
    parser = argparse.ArgumentParser(description="Trust decay model")
    parser.add_argument("--demo", action="store_true", help="Run demo")
    parser.add_argument("--compare", action="store_true", help="Compare models")
    parser.add_argument("--half-life", type=float, default=4.0)
    args = parser.parse_args()
    
    if args.compare:
        compare()
    else:
        demo()


if __name__ == "__main__":
    main()
