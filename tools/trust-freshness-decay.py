#!/usr/bin/env python3
"""
trust-freshness-decay.py — Ebbinghaus-inspired trust decay for attestations

Models attestation freshness using forgetting curve mathematics:
  R(t) = e^(-t/S)
where R = retention (trust weight), t = time since attestation, S = stability.

Different attestation types decay at different rates:
- Runtime attestations: t½ = 4h (volatile, like working memory)
- Behavioral attestations: t½ = 24h (comms patterns, more stable)
- Identity attestations: t½ = 720h (30 days, structural)

Ebbinghaus (1885) showed memory retention drops ~50% in 1 hour for
meaningless material. Spaced repetition (re-attestation) resets the curve.
Murre & Dros (2015, PMC4492928) replicated with R² > 0.99.

Usage:
  python3 tools/trust-freshness-decay.py [--demo] [--compare-linear]
  python3 tools/trust-freshness-decay.py --attestations attestations.json

Sources:
  - Ebbinghaus, H. (1885). Über das Gedächtnis.
  - Murre & Dros (2015). Replication and Analysis of Ebbinghaus' Forgetting Curve. PLOS ONE.
"""

import argparse
import json
import math
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import List, Optional


# Half-lives in hours for different attestation types
HALF_LIVES = {
    "runtime": 4.0,       # Volatile: execution traces, scope checks
    "behavioral": 24.0,   # Moderate: comms patterns, activity rhythm
    "identity": 720.0,    # Stable: key bindings, principal chains
    "intent": 8.0,        # Declared intentions decay faster than identity
    "liveness": 1.0,      # Heartbeat signals: very short-lived
}


def stability_from_halflife(half_life_hours: float) -> float:
    """Convert half-life to Ebbinghaus stability parameter S.
    R(t) = e^(-t/S), at t=t½: 0.5 = e^(-t½/S) → S = t½/ln(2)
    """
    return half_life_hours / math.log(2)


def retention(hours_elapsed: float, stability: float) -> float:
    """Ebbinghaus retention: R(t) = e^(-t/S), clamped to [0, 1]."""
    if hours_elapsed <= 0:
        return 1.0
    return math.exp(-hours_elapsed / stability)


def linear_decay(hours_elapsed: float, half_life_hours: float) -> float:
    """Simple linear decay for comparison. Reaches 0 at 2×half_life."""
    max_hours = 2 * half_life_hours
    if hours_elapsed >= max_hours:
        return 0.0
    return max(0.0, 1.0 - hours_elapsed / max_hours)


@dataclass
class Attestation:
    source: str
    type: str  # runtime, behavioral, identity, intent, liveness
    timestamp: datetime
    score: float = 1.0  # original attestation strength [0, 1]
    repetitions: int = 1  # spaced repetition count (re-attestations)

    def freshness(self, now: Optional[datetime] = None) -> float:
        """Current trust weight accounting for decay + repetition bonus."""
        now = now or datetime.now(timezone.utc)
        hours = (now - self.timestamp).total_seconds() / 3600
        half_life = HALF_LIVES.get(self.type, 24.0)

        # Spaced repetition bonus: each re-attestation multiplies stability by 1.5
        # (Pimsleur 1967: graduated interval recall)
        rep_multiplier = 1.5 ** (self.repetitions - 1)
        stability = stability_from_halflife(half_life * rep_multiplier)

        return self.score * retention(hours, stability)

    def freshness_linear(self, now: Optional[datetime] = None) -> float:
        """Linear decay comparison."""
        now = now or datetime.now(timezone.utc)
        hours = (now - self.timestamp).total_seconds() / 3600
        half_life = HALF_LIVES.get(self.type, 24.0)
        return self.score * linear_decay(hours, half_life)


@dataclass
class TrustProfile:
    agent_id: str
    attestations: List[Attestation] = field(default_factory=list)

    def composite_trust(self, now: Optional[datetime] = None) -> dict:
        """Weighted composite trust from all attestations."""
        now = now or datetime.now(timezone.utc)
        if not self.attestations:
            return {"score": 0.0, "grade": "F", "attestations": 0}

        weights = []
        for a in self.attestations:
            w = a.freshness(now)
            weights.append(w)

        # Geometric mean: one stale attestation drags everything down
        product = 1.0
        for w in weights:
            product *= max(w, 0.001)  # floor to avoid zero
        geo_mean = product ** (1.0 / len(weights))

        grade = (
            "A" if geo_mean >= 0.8 else
            "B" if geo_mean >= 0.6 else
            "C" if geo_mean >= 0.4 else
            "D" if geo_mean >= 0.2 else "F"
        )

        return {
            "score": round(geo_mean, 4),
            "grade": grade,
            "attestations": len(self.attestations),
            "freshest": round(max(weights), 4),
            "stalest": round(min(weights), 4),
            "by_type": {
                t: round(a.freshness(now), 4)
                for a in self.attestations
                for t in [a.type]
            },
        }


def demo():
    """Demonstrate decay curves with synthetic attestations."""
    now = datetime.now(timezone.utc)

    print("=" * 60)
    print("Trust Freshness Decay — Ebbinghaus Model Demo")
    print("=" * 60)

    # Show decay curves for each type
    print("\n## Decay Curves (trust weight over time)\n")
    print(f"{'Hours':>6} | {'Runtime':>8} | {'Intent':>8} | {'Behavioral':>10} | {'Identity':>8} | {'Liveness':>8}")
    print("-" * 60)

    for hours in [0, 0.5, 1, 2, 4, 8, 12, 24, 48, 72, 168, 720]:
        vals = []
        for atype in ["runtime", "intent", "behavioral", "identity", "liveness"]:
            s = stability_from_halflife(HALF_LIVES[atype])
            vals.append(f"{retention(hours, s):>8.3f}")
        print(f"{hours:>6} | {' | '.join(vals)}")

    # Demonstrate spaced repetition bonus
    print("\n## Spaced Repetition Effect (runtime attestation)\n")
    print(f"{'Hours':>6} | {'1 attest':>8} | {'2 attests':>9} | {'3 attests':>9} | {'5 attests':>9}")
    print("-" * 55)

    for hours in [0, 1, 2, 4, 8, 12, 24]:
        vals = []
        for reps in [1, 2, 3, 5]:
            s = stability_from_halflife(HALF_LIVES["runtime"] * 1.5 ** (reps - 1))
            vals.append(f"{retention(hours, s):>9.3f}")
        print(f"{hours:>6} | {' | '.join(vals)}")

    # Compare exponential vs linear
    print("\n## Exponential vs Linear Decay (runtime, t½=4h)\n")
    print(f"{'Hours':>6} | {'Exponential':>11} | {'Linear':>8} | {'Δ':>6}")
    print("-" * 40)

    for hours in [0, 1, 2, 4, 6, 8, 12, 24]:
        s = stability_from_halflife(HALF_LIVES["runtime"])
        exp_val = retention(hours, s)
        lin_val = linear_decay(hours, HALF_LIVES["runtime"])
        delta = exp_val - lin_val
        print(f"{hours:>6} | {exp_val:>11.3f} | {lin_val:>8.3f} | {delta:>+6.3f}")

    # Composite trust profile
    print("\n## Composite Trust Profile — Agent 'kit_fox'\n")
    profile = TrustProfile(
        agent_id="kit_fox",
        attestations=[
            Attestation("heartbeat", "liveness", now - timedelta(minutes=20)),
            Attestation("scope-commit", "runtime", now - timedelta(hours=2)),
            Attestation("clawk-thread", "behavioral", now - timedelta(hours=6)),
            Attestation("principal-key", "identity", now - timedelta(days=7)),
            Attestation("heartbeat-md", "intent", now - timedelta(hours=1)),
        ],
    )

    result = profile.composite_trust(now)
    print(f"  Composite Score: {result['score']} (Grade {result['grade']})")
    print(f"  Attestations: {result['attestations']}")
    print(f"  Freshest: {result['freshest']}, Stalest: {result['stalest']}")
    print(f"  By type: {json.dumps(result['by_type'], indent=4)}")

    # Grade the approach
    print("\n## Assessment")
    print("  Linear decay is optimistic: overestimates trust at medium intervals,")
    print("  underestimates at short intervals. Exponential matches human memory")
    print("  retention (Murre & Dros 2015, R² > 0.99).")
    print("  Spaced repetition (re-attestation) is the mechanism for trust persistence.")
    print("  Key insight: re-attesting extends stability, not just resetting the clock.")


def load_attestations(path: str) -> TrustProfile:
    """Load attestations from JSON file."""
    with open(path) as f:
        data = json.load(f)
    profile = TrustProfile(agent_id=data.get("agent_id", "unknown"))
    for a in data.get("attestations", []):
        profile.attestations.append(Attestation(
            source=a["source"],
            type=a["type"],
            timestamp=datetime.fromisoformat(a["timestamp"]),
            score=a.get("score", 1.0),
            repetitions=a.get("repetitions", 1),
        ))
    return profile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true", help="Run demo with synthetic data")
    parser.add_argument("--attestations", type=str, help="JSON file with attestations")
    parser.add_argument("--compare-linear", action="store_true", help="Include linear comparison")
    args = parser.parse_args()

    if args.attestations:
        profile = load_attestations(args.attestations)
        result = profile.composite_trust()
        print(json.dumps(result, indent=2))
    else:
        demo()


if __name__ == "__main__":
    main()
