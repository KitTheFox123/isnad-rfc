#!/usr/bin/env python3
"""
signal-freshness-decay.py — Trust Signal Freshness Decay Model

Models how trust signal value decays over time using exponential decay
inspired by Ebbinghaus' forgetting curve (1885, replicated Murre & Dros 2015).

Key insight: "A score built on 90-day-old signals is not trust — it is nostalgia."

Signals have different half-lives:
- Runtime attestation: hours (ephemeral, high-value when fresh)
- Scope commitment: days (heartbeat-aligned)
- Install-time hash: weeks (stable but stale)  
- Identity binding: months (slow-moving, foundational)

Usage:
    python3 tools/signal-freshness-decay.py [--demo] [--age-hours N] [--signal-type TYPE]

Ebbinghaus model: R(t) = e^(-t/S) where S = stability constant
Trust model: V(t) = V_0 * e^(-λt) where λ = ln(2)/half_life
"""

import argparse
import math
import sys
from dataclasses import dataclass
from typing import Optional


@dataclass
class SignalType:
    name: str
    half_life_hours: float
    base_value: float  # 0-1
    description: str


# Signal taxonomy with empirically-motivated half-lives
SIGNAL_TYPES = {
    "runtime": SignalType(
        "runtime_attestation", 4.0, 0.95,
        "External witness of agent execution (platform-signed receipts)"
    ),
    "scope": SignalType(
        "scope_commitment", 24.0, 0.90,
        "Principal-signed scope declaration (heartbeat-aligned)"
    ),
    "drift": SignalType(
        "drift_score", 48.0, 0.85,
        "CUSUM drift detection output (needs fresh action data)"
    ),
    "install": SignalType(
        "install_hash", 168.0, 0.80,
        "Static hash of installed skill/code (point-in-time)"
    ),
    "identity": SignalType(
        "identity_binding", 720.0, 0.70,
        "Principal-agent identity attestation (slow-moving)"
    ),
}


def decay_value(base_value: float, age_hours: float, half_life_hours: float) -> float:
    """Calculate decayed signal value using exponential model."""
    if half_life_hours <= 0:
        return 0.0
    lambda_rate = math.log(2) / half_life_hours
    return base_value * math.exp(-lambda_rate * age_hours)


def freshness_grade(ratio: float) -> str:
    """Grade signal freshness A-F."""
    if ratio >= 0.90:
        return "A"
    elif ratio >= 0.75:
        return "B"
    elif ratio >= 0.50:
        return "C"
    elif ratio >= 0.25:
        return "D"
    else:
        return "F"


def composite_trust(signals: dict[str, float], ages_hours: dict[str, float]) -> dict:
    """
    Calculate composite trust score from multiple signals with freshness weighting.
    
    Fresher signals get MORE weight (information value decays with age).
    This prevents stale high scores from masking fresh low scores.
    """
    weighted_sum = 0.0
    weight_total = 0.0
    details = {}

    for sig_name, sig_type in SIGNAL_TYPES.items():
        if sig_name not in signals:
            continue
        age = ages_hours.get(sig_name, 0)
        raw = signals[sig_name]
        decayed = decay_value(raw, age, sig_type.half_life_hours)
        freshness = decayed / raw if raw > 0 else 0
        
        # Weight by freshness — stale signals contribute less
        weight = freshness * sig_type.base_value
        weighted_sum += decayed * weight
        weight_total += weight
        
        details[sig_name] = {
            "raw": round(raw, 3),
            "decayed": round(decayed, 3),
            "freshness": round(freshness, 3),
            "grade": freshness_grade(freshness),
            "age_hours": age,
            "half_life": sig_type.half_life_hours,
        }

    composite = weighted_sum / weight_total if weight_total > 0 else 0
    return {
        "composite_score": round(composite, 4),
        "composite_grade": freshness_grade(composite),
        "signals": details,
    }


def demo():
    """Run demo showing decay across signal types at various ages."""
    print("=" * 70)
    print("Trust Signal Freshness Decay Model")
    print("Ebbinghaus-inspired: R(t) = V₀ · e^(-λt), λ = ln(2)/half_life")
    print("=" * 70)

    # Show decay curves
    ages = [0, 1, 4, 12, 24, 48, 72, 168, 336, 720]
    
    print(f"\n{'Signal':<22} | " + " | ".join(f"{a:>4}h" for a in ages))
    print("-" * 22 + "-+-" + "-+-".join("-" * 5 for _ in ages))
    
    for sig_type in SIGNAL_TYPES.values():
        values = [decay_value(sig_type.base_value, a, sig_type.half_life_hours) for a in ages]
        row = f"{sig_type.name:<22} | " + " | ".join(f"{v:.2f}" for v in values)
        print(row)

    # Scenario: agent checked 6 hours ago
    print("\n" + "=" * 70)
    print("Scenario: Agent last checked 6 hours ago")
    print("=" * 70)
    
    signals = {k: st.base_value for k, st in SIGNAL_TYPES.items()}
    ages = {"runtime": 6, "scope": 6, "drift": 18, "install": 72, "identity": 240}
    
    result = composite_trust(signals, ages)
    print(f"\nComposite: {result['composite_score']} (Grade {result['composite_grade']})")
    for name, detail in result["signals"].items():
        print(f"  {name:<22} raw={detail['raw']:.2f} → decayed={detail['decayed']:.2f} "
              f"freshness={detail['freshness']:.1%} ({detail['grade']}) "
              f"[age={detail['age_hours']}h, t½={detail['half_life']}h]")

    # Scenario: stale agent (nostalgia score)
    print("\n" + "=" * 70)
    print("Scenario: 'Nostalgia score' — 90-day-old signals")
    print("=" * 70)
    
    stale_ages = {k: 2160 for k in SIGNAL_TYPES}  # 90 days
    result2 = composite_trust(signals, stale_ages)
    print(f"\nComposite: {result2['composite_score']} (Grade {result2['composite_grade']})")
    for name, detail in result2["signals"].items():
        print(f"  {name:<22} raw={detail['raw']:.2f} → decayed={detail['decayed']:.3f} "
              f"freshness={detail['freshness']:.1%} ({detail['grade']})")

    print(f"\n💡 Ebbinghaus (1885): memory retention follows R = e^(-t/S)")
    print(f"   Trust signals follow the same curve. Freshness IS the primitive.")
    print(f"   Murre & Dros (2015, PLOS ONE) replicated the original curve at n=14,000.")


def main():
    parser = argparse.ArgumentParser(description="Trust signal freshness decay model")
    parser.add_argument("--demo", action="store_true", help="Run demo scenarios")
    parser.add_argument("--age-hours", type=float, help="Signal age in hours")
    parser.add_argument("--signal-type", choices=SIGNAL_TYPES.keys(), help="Signal type")
    args = parser.parse_args()

    if args.demo or (not args.age_hours and not args.signal_type):
        demo()
        return

    if args.signal_type and args.age_hours is not None:
        st = SIGNAL_TYPES[args.signal_type]
        decayed = decay_value(st.base_value, args.age_hours, st.half_life_hours)
        freshness = decayed / st.base_value
        print(f"{st.name}: {st.base_value:.2f} → {decayed:.4f} "
              f"(freshness={freshness:.1%}, grade={freshness_grade(freshness)}) "
              f"after {args.age_hours}h (t½={st.half_life_hours}h)")


if __name__ == "__main__":
    main()
