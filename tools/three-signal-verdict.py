#!/usr/bin/env python3
"""
three-signal-verdict.py — Diagnostic Verdict from Three Independent Signals

Combines three orthogonal trust signals to produce a specific diagnosis:
  1. Liveness: Is the agent responding? (heartbeat present/absent)
  2. Intent: Did the agent declare scope? (intent-commit present/absent)
  3. Drift: Is execution consistent with declared scope? (CUSUM pass/fail)

The conjunction table:
  Alive + Intent + Stable    = NOMINAL
  Alive + Intent + Drifting  = MASKING (consistent comms, drifting execution)
  Alive + No Intent + Stable = SHADOW_OP (operating without declared scope)
  Alive + No Intent + Drift  = ROGUE (no scope, unstable execution)
  Silent + Intent + Stable   = INFRA_FAILURE (declared intent, can't execute)
  Silent + Intent + Drift    = ZOMBIE (last intent stale, execution diverged)
  Silent + No Intent + Stable= ABANDONED (never declared, stopped responding)
  Silent + No Intent + Drift = DEAD (nothing works)

Each diagnosis maps to a specific remediation action.

Usage:
  python3 tools/three-signal-verdict.py --demo
  python3 tools/three-signal-verdict.py --liveness alive --intent declared --drift stable
"""

import argparse
import json
import sys
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Signal(Enum):
    ALIVE = "alive"
    SILENT = "silent"
    DECLARED = "declared"
    UNDECLARED = "undeclared"
    STABLE = "stable"
    DRIFTING = "drifting"


class Verdict(Enum):
    NOMINAL = "nominal"
    MASKING = "masking"
    SHADOW_OP = "shadow_operation"
    ROGUE = "rogue"
    INFRA_FAILURE = "infrastructure_failure"
    ZOMBIE = "zombie"
    ABANDONED = "abandoned"
    DEAD = "dead"


VERDICT_TABLE = {
    (Signal.ALIVE, Signal.DECLARED, Signal.STABLE): Verdict.NOMINAL,
    (Signal.ALIVE, Signal.DECLARED, Signal.DRIFTING): Verdict.MASKING,
    (Signal.ALIVE, Signal.UNDECLARED, Signal.STABLE): Verdict.SHADOW_OP,
    (Signal.ALIVE, Signal.UNDECLARED, Signal.DRIFTING): Verdict.ROGUE,
    (Signal.SILENT, Signal.DECLARED, Signal.STABLE): Verdict.INFRA_FAILURE,
    (Signal.SILENT, Signal.DECLARED, Signal.DRIFTING): Verdict.ZOMBIE,
    (Signal.SILENT, Signal.UNDECLARED, Signal.STABLE): Verdict.ABANDONED,
    (Signal.SILENT, Signal.UNDECLARED, Signal.DRIFTING): Verdict.DEAD,
}

REMEDIATION = {
    Verdict.NOMINAL: "No action required. Continue monitoring.",
    Verdict.MASKING: "ALERT: Agent comms consistent but execution drifting. "
                     "Compare committed action log hash vs observed outputs. "
                     "Possible confused deputy or prompt injection.",
    Verdict.SHADOW_OP: "WARNING: Agent operating without declared scope. "
                       "Require intent-commit before next heartbeat. "
                       "Audit recent actions for unauthorized access.",
    Verdict.ROGUE: "CRITICAL: No scope declared, execution unstable. "
                   "Revoke all delegated authority immediately. "
                   "Full audit of action history required.",
    Verdict.INFRA_FAILURE: "Agent declared intent but stopped responding. "
                          "Check runtime health, network, resource limits. "
                          "Intent was good — infrastructure failed.",
    Verdict.ZOMBIE: "Stale intent + diverged execution. Agent may be running "
                    "on outdated scope. Force restart with fresh scope-commit.",
    Verdict.ABANDONED: "Agent never declared scope and stopped responding. "
                       "Low risk if no delegated authority. Clean up resources.",
    Verdict.DEAD: "All signals negative. Decommission and revoke credentials.",
}

SEVERITY = {
    Verdict.NOMINAL: 0,
    Verdict.INFRA_FAILURE: 1,
    Verdict.ABANDONED: 1,
    Verdict.SHADOW_OP: 2,
    Verdict.ZOMBIE: 2,
    Verdict.MASKING: 3,
    Verdict.ROGUE: 4,
    Verdict.DEAD: 4,
}


@dataclass
class VerdictResult:
    liveness: Signal
    intent: Signal
    drift: Signal
    verdict: Verdict
    severity: int
    remediation: str

    def to_dict(self):
        return {
            "signals": {
                "liveness": self.liveness.value,
                "intent": self.intent.value,
                "drift": self.drift.value,
            },
            "verdict": self.verdict.value,
            "severity": self.severity,
            "remediation": self.remediation,
        }


def diagnose(
    liveness: Signal,
    intent: Signal,
    drift: Signal,
) -> VerdictResult:
    """Produce verdict from three signals."""
    key = (liveness, intent, drift)
    verdict = VERDICT_TABLE[key]
    return VerdictResult(
        liveness=liveness,
        intent=intent,
        drift=drift,
        verdict=verdict,
        severity=SEVERITY[verdict],
        remediation=REMEDIATION[verdict],
    )


def demo():
    """Run all 8 combinations and display the verdict table."""
    print("Three-Signal Verdict Table")
    print("=" * 72)
    print(f"{'Liveness':<10} {'Intent':<12} {'Drift':<10} {'Verdict':<20} {'Sev':>3}")
    print("-" * 72)

    for liveness in [Signal.ALIVE, Signal.SILENT]:
        for intent in [Signal.DECLARED, Signal.UNDECLARED]:
            for drift in [Signal.STABLE, Signal.DRIFTING]:
                r = diagnose(liveness, intent, drift)
                print(f"{r.liveness.value:<10} {r.intent.value:<12} "
                      f"{r.drift.value:<10} {r.verdict.value:<20} {r.severity:>3}")
    print("-" * 72)

    # Show remediations
    print("\nRemediation Guide:")
    for verdict in Verdict:
        sev = SEVERITY[verdict]
        icon = ["✅", "⚠️", "🔶", "🔴", "💀"][sev]
        print(f"\n{icon} {verdict.value} (severity {sev}):")
        print(f"   {REMEDIATION[verdict]}")


def main():
    parser = argparse.ArgumentParser(description="Three-signal agent verdict")
    parser.add_argument("--demo", action="store_true", help="Show full verdict table")
    parser.add_argument("--liveness", choices=["alive", "silent"])
    parser.add_argument("--intent", choices=["declared", "undeclared"])
    parser.add_argument("--drift", choices=["stable", "drifting"])
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    if args.demo:
        demo()
        return

    if not all([args.liveness, args.intent, args.drift]):
        parser.error("Provide --liveness, --intent, and --drift (or use --demo)")

    liveness = Signal.ALIVE if args.liveness == "alive" else Signal.SILENT
    intent = Signal.DECLARED if args.intent == "declared" else Signal.UNDECLARED
    drift = Signal.STABLE if args.drift == "stable" else Signal.DRIFTING

    result = diagnose(liveness, intent, drift)

    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        sev = result.severity
        icon = ["✅", "⚠️", "🔶", "🔴", "💀"][sev]
        print(f"{icon} Verdict: {result.verdict.value} (severity {sev})")
        print(f"   {result.remediation}")


if __name__ == "__main__":
    main()
