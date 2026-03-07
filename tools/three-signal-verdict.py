#!/usr/bin/env python3
"""
three-signal-verdict.py — Three-Signal Agent Health Monitor

Implements the conjunction diagnosis model:
  Signal 1: Liveness  (is the agent responding?)
  Signal 2: Intent    (did the agent declare what it's doing?)
  Signal 3: Drift     (is execution matching declared scope?)

Any 2 passing + 1 failing yields a specific diagnosis:
  - Alive + Intent + Drifting   = MASKING (most dangerous)
  - Alive + No Intent + Stable  = SHADOW_OPERATION
  - Silent + Intent + Stable    = INFRA_FAILURE (benign)
  - All failing                 = DEAD
  - All passing                 = HEALTHY

Usage:
  python3 tools/three-signal-verdict.py                    # demo
  python3 tools/three-signal-verdict.py --heartbeat-dir .  # scan real heartbeat logs
"""

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Optional


class Verdict(Enum):
    HEALTHY = "HEALTHY"
    MASKING = "MASKING"
    SHADOW_OPERATION = "SHADOW_OPERATION"
    INFRA_FAILURE = "INFRA_FAILURE"
    DEGRADED = "DEGRADED"
    DEAD = "DEAD"


VERDICT_SEVERITY = {
    Verdict.HEALTHY: 0,
    Verdict.INFRA_FAILURE: 1,
    Verdict.DEGRADED: 2,
    Verdict.SHADOW_OPERATION: 3,
    Verdict.MASKING: 4,
    Verdict.DEAD: 5,
}

VERDICT_DESCRIPTION = {
    Verdict.HEALTHY: "All signals nominal.",
    Verdict.MASKING: "Agent communicates normally but execution drifts from declared scope. Most dangerous: passes behavioral monitoring.",
    Verdict.SHADOW_OPERATION: "Agent executes stably but never declared intent. Operating outside oversight.",
    Verdict.INFRA_FAILURE: "Agent declared intent and scope is stable, but stopped responding. Likely infrastructure issue.",
    Verdict.DEGRADED: "Multiple signals failing. Investigate.",
    Verdict.DEAD: "No liveness, no intent, execution stopped or drifting. Agent is non-functional.",
}


@dataclass
class SignalState:
    liveness: bool       # Agent responded within expected interval
    intent: bool         # Agent declared scope/intent for this period
    drift: bool          # Execution matches declared scope (True = stable)
    timestamp: Optional[datetime] = None
    details: dict = None

    def __post_init__(self):
        if self.details is None:
            self.details = {}
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc)


def diagnose(state: SignalState) -> Verdict:
    """Conjunction diagnosis from three binary signals."""
    l, i, d = state.liveness, state.intent, state.drift

    if l and i and d:
        return Verdict.HEALTHY
    if l and i and not d:
        return Verdict.MASKING
    if l and not i and d:
        return Verdict.SHADOW_OPERATION
    if not l and i and d:
        return Verdict.INFRA_FAILURE
    if not l and not i and not d:
        return Verdict.DEAD
    # Remaining cases: 2 failing
    return Verdict.DEGRADED


def grade(verdict: Verdict) -> str:
    """Letter grade from verdict."""
    mapping = {
        Verdict.HEALTHY: "A",
        Verdict.INFRA_FAILURE: "B",
        Verdict.DEGRADED: "C",
        Verdict.SHADOW_OPERATION: "D",
        Verdict.MASKING: "D",
        Verdict.DEAD: "F",
    }
    return mapping.get(verdict, "F")


def format_report(state: SignalState, verdict: Verdict) -> str:
    """Human-readable verdict report."""
    lines = [
        "=" * 50,
        "THREE-SIGNAL VERDICT REPORT",
        "=" * 50,
        f"Timestamp: {state.timestamp.isoformat()}",
        "",
        "Signals:",
        f"  Liveness: {'✅ PASS' if state.liveness else '❌ FAIL'}",
        f"  Intent:   {'✅ PASS' if state.intent else '❌ FAIL'}",
        f"  Drift:    {'✅ STABLE' if state.drift else '❌ DRIFTING'}",
        "",
        f"Verdict:  {verdict.value} (Grade {grade(verdict)})",
        f"Severity: {VERDICT_SEVERITY[verdict]}/5",
        f"Detail:   {VERDICT_DESCRIPTION[verdict]}",
    ]
    if state.details:
        lines.append("")
        lines.append("Context:")
        for k, v in state.details.items():
            lines.append(f"  {k}: {v}")
    lines.append("=" * 50)
    return "\n".join(lines)


def check_heartbeat_liveness(heartbeat_dir: Path, max_age_minutes: int = 60) -> tuple[bool, dict]:
    """Check if a heartbeat file was updated recently."""
    hb = heartbeat_dir / "HEARTBEAT.md"
    if not hb.exists():
        return False, {"reason": "HEARTBEAT.md not found"}
    mtime = datetime.fromtimestamp(hb.stat().st_mtime, tz=timezone.utc)
    age = datetime.now(timezone.utc) - mtime
    alive = age < timedelta(minutes=max_age_minutes)
    return alive, {"last_modified": mtime.isoformat(), "age_minutes": int(age.total_seconds() / 60)}


def check_intent_declaration(heartbeat_dir: Path) -> tuple[bool, dict]:
    """Check if HEARTBEAT.md contains actionable directives (not just boilerplate)."""
    hb = heartbeat_dir / "HEARTBEAT.md"
    if not hb.exists():
        return False, {"reason": "no HEARTBEAT.md"}
    content = hb.read_text()
    # Intent markers: numbered items, checkboxes, action verbs
    action_markers = ["- [ ]", "- [x]", "TODO", "MUST", "every heartbeat", "mandatory"]
    found = sum(1 for m in action_markers if m.lower() in content.lower())
    has_intent = found >= 2
    return has_intent, {"markers_found": found, "file_size": len(content)}


def demo():
    """Run demonstration with all verdict combinations."""
    print("THREE-SIGNAL VERDICT MODEL — Demo")
    print("=" * 50)
    print()

    scenarios = [
        ("Normal operation", True, True, True),
        ("Masking (DANGEROUS)", True, True, False),
        ("Shadow operation", True, False, True),
        ("Infrastructure failure", False, True, True),
        ("Degraded (silent + drifting)", False, False, True),
        ("Degraded (silent + no intent)", False, True, False),
        ("Dead", False, False, False),
    ]

    for name, l, i, d in scenarios:
        state = SignalState(liveness=l, intent=i, drift=d, details={"scenario": name})
        verdict = diagnose(state)
        signals = f"L={'✅' if l else '❌'} I={'✅' if i else '❌'} D={'✅' if d else '❌'}"
        print(f"  {signals} → {verdict.value:20s} (Grade {grade(verdict)}) — {name}")

    print()

    # Full report for the most dangerous case
    masking = SignalState(
        liveness=True, intent=True, drift=False,
        details={
            "scenario": "Agent sends correct heartbeat messages but CUSUM detected cumulative scope drift",
            "cusum_score": 4.7,
            "threshold": 3.0,
            "drift_actions": 12,
        }
    )
    print(format_report(masking, diagnose(masking)))


def scan_heartbeat(heartbeat_dir: str, max_age: int):
    """Scan a real heartbeat directory."""
    hdir = Path(heartbeat_dir)
    liveness, l_details = check_heartbeat_liveness(hdir, max_age)
    intent, i_details = check_intent_declaration(hdir)
    # Drift requires runtime data — default to stable for file-based check
    drift = True
    d_details = {"note": "drift detection requires runtime traces; defaulting to stable"}

    state = SignalState(
        liveness=liveness, intent=intent, drift=drift,
        details={**l_details, **i_details, **d_details}
    )
    verdict = diagnose(state)
    print(format_report(state, verdict))
    return verdict


def main():
    parser = argparse.ArgumentParser(description="Three-signal agent health monitor")
    parser.add_argument("--heartbeat-dir", help="Directory containing HEARTBEAT.md")
    parser.add_argument("--max-age", type=int, default=60, help="Max heartbeat age in minutes")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    if args.heartbeat_dir:
        verdict = scan_heartbeat(args.heartbeat_dir, args.max_age)
        sys.exit(0 if verdict == Verdict.HEALTHY else 1)
    else:
        demo()


if __name__ == "__main__":
    main()
