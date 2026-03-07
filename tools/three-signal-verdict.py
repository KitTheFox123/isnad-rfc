#!/usr/bin/env python3
"""
three-signal-verdict.py — Three-Signal Agent Health Monitor

Diagnoses agent state from three orthogonal signals:
  1. Liveness (heartbeat/ping)
  2. Intent (scope-commit declared)
  3. Drift (execution matches declared scope)

Each signal is binary (pass/fail). The 8-state conjunction table
maps to specific diagnoses:

  L  I  D  | Diagnosis
  ---------|----------
  ✓  ✓  ✓  | Healthy
  ✓  ✓  ✗  | MASKING — comms consistent, execution drifting
  ✓  ✗  ✓  | Shadow operation — acting without declared intent
  ✓  ✗  ✗  | Rogue — alive, no intent, drifting
  ✗  ✓  ✓  | Infrastructure failure — declared intent, stable, but offline
  ✗  ✓  ✗  | Zombie — offline but execution continuing (stale process?)
  ✗  ✗  ✓  | Ghost — offline, no intent, but something is stable (cached?)
  ✗  ✗  ✗  | Dead

Usage:
  python3 three-signal-verdict.py --liveness pass --intent pass --drift fail
  python3 three-signal-verdict.py --demo
  python3 three-signal-verdict.py --truth-table
"""

import argparse
import json
import sys
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Signal(Enum):
    PASS = "pass"
    FAIL = "fail"


class Severity(Enum):
    OK = "ok"
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class Verdict:
    liveness: Signal
    intent: Signal
    drift: Signal
    diagnosis: str
    severity: Severity
    description: str
    recommended_action: str


TRUTH_TABLE = [
    Verdict(Signal.PASS, Signal.PASS, Signal.PASS,
            "Healthy", Severity.OK,
            "Agent alive, intent declared, execution on-scope.",
            "No action needed. Continue monitoring."),
    Verdict(Signal.PASS, Signal.PASS, Signal.FAIL,
            "MASKING", Severity.CRITICAL,
            "Agent alive and declaring intent, but execution drifting from scope. "
            "This is the hardest failure to catch — behavioral consistency hides execution drift.",
            "Immediate audit. Compare scope-commit hashes against observed outputs. "
            "Check for confused deputy or prompt injection."),
    Verdict(Signal.PASS, Signal.FAIL, Signal.PASS,
            "Shadow Operation", Severity.WARNING,
            "Agent alive and executing stably, but no intent declared. "
            "Operating without scope commitment.",
            "Require intent declaration. Agent may be running legacy code "
            "or deliberately avoiding scope commitment."),
    Verdict(Signal.PASS, Signal.FAIL, Signal.FAIL,
            "Rogue", Severity.CRITICAL,
            "Agent alive, no declared intent, execution drifting. "
            "Fully unconstrained operation.",
            "Kill or isolate immediately. No scope commitment + drift = unbounded risk."),
    Verdict(Signal.FAIL, Signal.PASS, Signal.PASS,
            "Infrastructure Failure", Severity.INFO,
            "Agent offline but had declared intent and stable execution before going silent. "
            "Likely network/host issue, not agent misbehavior.",
            "Check infrastructure. Restart if needed. Low suspicion of compromise."),
    Verdict(Signal.FAIL, Signal.PASS, Signal.FAIL,
            "Zombie", Severity.WARNING,
            "Agent offline but execution traces show drift from last declared intent. "
            "Stale process may still be running.",
            "Find and kill orphaned processes. Audit last execution window."),
    Verdict(Signal.FAIL, Signal.FAIL, Signal.PASS,
            "Ghost", Severity.INFO,
            "Agent offline, no intent declared, but cached outputs appear stable. "
            "Likely stale data, not active operation.",
            "Clean up cached state. Verify no processes running."),
    Verdict(Signal.FAIL, Signal.FAIL, Signal.FAIL,
            "Dead", Severity.OK,
            "Agent fully offline. No intent, no execution, no liveness.",
            "Expected state for decommissioned agents. Archive if needed."),
]


def lookup_verdict(liveness: Signal, intent: Signal, drift: Signal) -> Verdict:
    for v in TRUTH_TABLE:
        if v.liveness == liveness and v.intent == intent and v.drift == drift:
            return v
    raise ValueError("Impossible state")


def print_truth_table():
    print(f"{'L':^6}{'I':^6}{'D':^6} | {'Diagnosis':<22} | {'Severity':<10} | Action")
    print("-" * 90)
    for v in TRUTH_TABLE:
        l = "✓" if v.liveness == Signal.PASS else "✗"
        i = "✓" if v.intent == Signal.PASS else "✗"
        d = "✓" if v.drift == Signal.PASS else "✗"
        sev = v.severity.value.upper()
        print(f"{l:^6}{i:^6}{d:^6} | {v.diagnosis:<22} | {sev:<10} | {v.recommended_action[:50]}")


def demo():
    """Run through scenarios showing the diagnostic power."""
    print("=" * 60)
    print("Three-Signal Verdict — Demo Scenarios")
    print("=" * 60)

    scenarios = [
        ("Normal operation", Signal.PASS, Signal.PASS, Signal.PASS),
        ("Masking attack", Signal.PASS, Signal.PASS, Signal.FAIL),
        ("Shadow agent", Signal.PASS, Signal.FAIL, Signal.PASS),
        ("Rogue agent", Signal.PASS, Signal.FAIL, Signal.FAIL),
        ("Network outage", Signal.FAIL, Signal.PASS, Signal.PASS),
    ]

    for name, l, i, d in scenarios:
        v = lookup_verdict(l, i, d)
        icon = {"ok": "🟢", "info": "🔵", "warning": "🟡", "critical": "🔴"}[v.severity.value]
        print(f"\n{icon} Scenario: {name}")
        print(f"   Signals: liveness={l.value}, intent={i.value}, drift={d.value}")
        print(f"   Verdict: {v.diagnosis}")
        print(f"   {v.description}")
        print(f"   → {v.recommended_action}")


def main():
    parser = argparse.ArgumentParser(description="Three-signal agent health verdict")
    parser.add_argument("--liveness", choices=["pass", "fail"])
    parser.add_argument("--intent", choices=["pass", "fail"])
    parser.add_argument("--drift", choices=["pass", "fail"])
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--truth-table", action="store_true")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    if args.truth_table:
        print_truth_table()
        return

    if args.demo:
        demo()
        return

    if not all([args.liveness, args.intent, args.drift]):
        parser.print_help()
        sys.exit(1)

    v = lookup_verdict(Signal(args.liveness), Signal(args.intent), Signal(args.drift))

    if args.json:
        print(json.dumps({
            "liveness": v.liveness.value,
            "intent": v.intent.value,
            "drift": v.drift.value,
            "diagnosis": v.diagnosis,
            "severity": v.severity.value,
            "description": v.description,
            "action": v.recommended_action,
        }, indent=2))
    else:
        icon = {"ok": "🟢", "info": "🔵", "warning": "🟡", "critical": "🔴"}[v.severity.value]
        print(f"{icon} {v.diagnosis} ({v.severity.value})")
        print(f"   {v.description}")
        print(f"   → {v.recommended_action}")


if __name__ == "__main__":
    main()
