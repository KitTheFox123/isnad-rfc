#!/usr/bin/env python3
"""
three-signal-verdict.py — Three-Signal Agent Health Monitor

Implements the conjunction diagnostic from the Kit/santaclawd/gendolf
Clawk thread (2026-03-07): liveness × intent × drift.

Any 2 passing + 1 failing = specific diagnosis:
  - Alive + intent declared + drifting execution = MASKING
  - Alive + no intent declared + stable execution = SHADOW_OP
  - Silent + intent declared + stable execution = INFRA_FAILURE
  - All failing = COMPROMISED
  - All passing = HEALTHY

Each signal has configurable staleness thresholds.

Usage:
    python3 tools/three-signal-verdict.py --demo
    python3 tools/three-signal-verdict.py --liveness 120 --intent true --drift 0.3
"""

import argparse
import json
import sys
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Verdict(Enum):
    HEALTHY = "HEALTHY"
    MASKING = "MASKING"                # alive + intent + drift
    SHADOW_OP = "SHADOW_OP"            # alive + no intent + stable
    INFRA_FAILURE = "INFRA_FAILURE"    # silent + intent + stable
    DEGRADED = "DEGRADED"              # 2 failing
    COMPROMISED = "COMPROMISED"        # all 3 failing


@dataclass
class SignalState:
    """State of a single monitoring signal."""
    name: str
    passing: bool
    value: float          # raw measurement
    threshold: float      # pass/fail boundary
    staleness_sec: float  # age of measurement
    max_staleness: float  # maximum acceptable age

    @property
    def stale(self) -> bool:
        return self.staleness_sec > self.max_staleness

    @property
    def effective(self) -> bool:
        """A signal passes only if it's passing AND fresh."""
        return self.passing and not self.stale


@dataclass
class VerdictResult:
    verdict: Verdict
    signals: dict
    diagnosis: str
    confidence: float  # 0-1, based on signal freshness
    timestamp: float

    def to_dict(self):
        return {
            "verdict": self.verdict.value,
            "signals": self.signals,
            "diagnosis": self.diagnosis,
            "confidence": round(self.confidence, 3),
            "timestamp": self.timestamp,
        }


def compute_verdict(
    liveness_age_sec: float,
    liveness_max: float = 300.0,       # 5 min default
    intent_declared: bool = True,
    intent_staleness: float = 0.0,
    intent_max: float = 3600.0,        # 1 hour
    drift_score: float = 0.0,          # 0 = no drift, 1 = max drift
    drift_threshold: float = 0.5,
    drift_staleness: float = 0.0,
    drift_max: float = 600.0,          # 10 min
) -> VerdictResult:
    """Compute three-signal verdict."""

    now = time.time()

    liveness = SignalState(
        name="liveness",
        passing=liveness_age_sec <= liveness_max,
        value=liveness_age_sec,
        threshold=liveness_max,
        staleness_sec=0,  # liveness IS its own staleness
        max_staleness=liveness_max,
    )

    intent = SignalState(
        name="intent",
        passing=intent_declared,
        value=1.0 if intent_declared else 0.0,
        threshold=0.5,
        staleness_sec=intent_staleness,
        max_staleness=intent_max,
    )

    drift = SignalState(
        name="drift",
        passing=drift_score < drift_threshold,
        value=drift_score,
        threshold=drift_threshold,
        staleness_sec=drift_staleness,
        max_staleness=drift_max,
    )

    signals = [liveness, intent, drift]
    passing_count = sum(1 for s in signals if s.effective)
    stale_count = sum(1 for s in signals if s.stale)

    # Confidence degrades with staleness
    freshness_scores = [
        max(0, 1 - s.staleness_sec / s.max_staleness) for s in signals
    ]
    confidence = sum(freshness_scores) / len(freshness_scores)

    # Determine verdict
    l, i, d = liveness.effective, intent.effective, drift.effective

    if l and i and d:
        verdict = Verdict.HEALTHY
        diagnosis = "All signals nominal."
    elif l and i and not d:
        verdict = Verdict.MASKING
        diagnosis = (
            f"Agent alive and declaring intent but execution drifting "
            f"(score={drift_score:.2f}, threshold={drift_threshold:.2f}). "
            f"Consistent comms + drifting execution = masking behavior."
        )
    elif l and not i and d:
        verdict = Verdict.SHADOW_OP
        diagnosis = (
            "Agent alive with stable execution but no intent declared. "
            "Operating outside declared scope — shadow operation."
        )
    elif not l and i and d:
        verdict = Verdict.INFRA_FAILURE
        diagnosis = (
            f"Agent silent (last seen {liveness_age_sec:.0f}s ago) but "
            f"intent declared and execution stable. Likely infrastructure failure."
        )
    elif passing_count == 1:
        verdict = Verdict.DEGRADED
        diagnosis = f"Only {passing_count}/3 signals passing. Multiple failures detected."
    else:
        verdict = Verdict.COMPROMISED
        diagnosis = "All signals failing. Agent may be compromised or fully offline."

    signal_dict = {}
    for s in signals:
        signal_dict[s.name] = {
            "passing": s.passing,
            "effective": s.effective,
            "value": round(s.value, 3),
            "threshold": s.threshold,
            "stale": s.stale,
        }

    return VerdictResult(
        verdict=verdict,
        signals=signal_dict,
        diagnosis=diagnosis,
        confidence=confidence,
        timestamp=now,
    )


def run_demo():
    """Demonstrate all verdict types."""
    scenarios = [
        ("HEALTHY", dict(liveness_age_sec=30, intent_declared=True, drift_score=0.1)),
        ("MASKING", dict(liveness_age_sec=30, intent_declared=True, drift_score=0.8)),
        ("SHADOW_OP", dict(liveness_age_sec=30, intent_declared=False, drift_score=0.1)),
        ("INFRA_FAILURE", dict(liveness_age_sec=600, intent_declared=True, drift_score=0.1)),
        ("COMPROMISED", dict(liveness_age_sec=600, intent_declared=False, drift_score=0.8)),
    ]

    print("Three-Signal Verdict Demo")
    print("=" * 60)

    for label, kwargs in scenarios:
        result = compute_verdict(**kwargs)
        icon = {
            Verdict.HEALTHY: "✅",
            Verdict.MASKING: "🎭",
            Verdict.SHADOW_OP: "👻",
            Verdict.INFRA_FAILURE: "🔧",
            Verdict.DEGRADED: "⚠️",
            Verdict.COMPROMISED: "💀",
        }.get(result.verdict, "?")

        print(f"\n{icon} Scenario: {label}")
        print(f"   Verdict: {result.verdict.value}")
        print(f"   Confidence: {result.confidence:.1%}")
        print(f"   Diagnosis: {result.diagnosis[:100]}")
        for name, sig in result.signals.items():
            status = "✓" if sig["effective"] else "✗"
            print(f"   {status} {name}: {sig['value']} (threshold: {sig['threshold']})")

    print("\n" + "=" * 60)
    print("Conjunction table: the monitor IS the diagnosis.")


def main():
    parser = argparse.ArgumentParser(description="Three-signal agent health verdict")
    parser.add_argument("--demo", action="store_true", help="Run demo scenarios")
    parser.add_argument("--liveness", type=float, help="Seconds since last heartbeat")
    parser.add_argument("--intent", type=str, help="Intent declared (true/false)")
    parser.add_argument("--drift", type=float, help="Drift score 0-1")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    if args.demo:
        run_demo()
        return

    if args.liveness is not None:
        result = compute_verdict(
            liveness_age_sec=args.liveness,
            intent_declared=args.intent.lower() == "true" if args.intent else True,
            drift_score=args.drift if args.drift is not None else 0.0,
        )
        if args.json:
            print(json.dumps(result.to_dict(), indent=2))
        else:
            icon = {"HEALTHY": "✅", "MASKING": "🎭", "SHADOW_OP": "👻",
                    "INFRA_FAILURE": "🔧", "DEGRADED": "⚠️", "COMPROMISED": "💀"}
            print(f"{icon.get(result.verdict.value, '?')} {result.verdict.value} "
                  f"(confidence: {result.confidence:.1%})")
            print(f"   {result.diagnosis}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
