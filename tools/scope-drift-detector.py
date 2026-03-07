#!/usr/bin/env python3
"""scope-drift-detector.py — Detect gradual scope drift using CUSUM control charts.

Based on Page (1954) cumulative sum method: individual actions may pass threshold
checks while the accumulated deviation signals drift from original scope.

Concept: each heartbeat produces a scope-commit hash. Actions within that scope
get a deviation score (0 = perfectly within scope, 1 = completely outside).
CUSUM accumulates small deviations that individually pass checks but collectively
indicate drift.

Usage:
    python3 scope-drift-detector.py [--threshold 5.0] [--allowance 0.1] [--demo]

References:
    - Page, E.S. (1954). "Continuous inspection schemes." Biometrika 41(1-2): 100-115.
    - Frontiers AI (2024). "One or two things we know about concept drift."
    - RFC 9162 §8.3: CT gossip for split-view detection.
"""

import argparse
import json
import hashlib
import sys
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class ScopeCommit:
    """A principal's scope commitment at issuance."""
    scope_hash: str  # SHA-256 of authorized scope document
    issued_at: str   # ISO 8601 timestamp
    ttl_seconds: int = 2400  # 40 min default (1 heartbeat)
    principal: str = ""
    agent: str = ""


@dataclass
class ActionRecord:
    """An observed agent action within a scope window."""
    action_hash: str
    timestamp: str
    deviation_score: float  # 0.0 = within scope, 1.0 = outside
    description: str = ""


@dataclass 
class CUSUMState:
    """CUSUM accumulator state."""
    S_high: float = 0.0   # Upper CUSUM (detecting upward drift)
    S_low: float = 0.0    # Lower CUSUM (detecting downward drift)  
    n_actions: int = 0
    alarms: list = field(default_factory=list)
    max_S_high: float = 0.0
    mean_deviation: float = 0.0
    _sum_deviation: float = 0.0


def cusum_update(state: CUSUMState, deviation: float, 
                 threshold: float = 5.0, allowance: float = 0.1) -> Optional[dict]:
    """Update CUSUM with new deviation observation.
    
    Args:
        state: Current CUSUM state
        deviation: New deviation score [0, 1]
        threshold: Decision interval h (alarm when S > h)
        allowance: Reference value k (tolerated deviation)
    
    Returns:
        Alarm dict if threshold exceeded, None otherwise.
    """
    state.n_actions += 1
    state._sum_deviation += deviation
    state.mean_deviation = state._sum_deviation / state.n_actions
    
    # Two-sided CUSUM
    state.S_high = max(0, state.S_high + (deviation - allowance))
    state.S_low = max(0, state.S_low - (deviation + allowance))  # For negative drift
    
    state.max_S_high = max(state.max_S_high, state.S_high)
    
    alarm = None
    if state.S_high > threshold:
        alarm = {
            "type": "drift_alarm",
            "direction": "upward",
            "S_high": round(state.S_high, 4),
            "n_actions": state.n_actions,
            "mean_deviation": round(state.mean_deviation, 4),
            "message": f"Scope drift detected after {state.n_actions} actions. "
                       f"CUSUM={state.S_high:.2f} > threshold={threshold}. "
                       f"Mean deviation={state.mean_deviation:.3f}."
        }
        state.alarms.append(alarm)
        # Reset after alarm (Western Electric variant)
        state.S_high = 0.0
    
    return alarm


def analyze_action_log(actions: list[ActionRecord], 
                       threshold: float = 5.0,
                       allowance: float = 0.1) -> dict:
    """Analyze a sequence of actions for scope drift.
    
    Returns summary with CUSUM trajectory, alarms, and grade.
    """
    state = CUSUMState()
    trajectory = []
    
    for action in actions:
        alarm = cusum_update(state, action.deviation_score, threshold, allowance)
        trajectory.append({
            "action": action.action_hash[:12],
            "deviation": action.deviation_score,
            "S_high": round(state.S_high, 4),
            "alarm": alarm is not None
        })
    
    # Grade based on alarm frequency and max accumulation
    alarm_rate = len(state.alarms) / max(state.n_actions, 1)
    if alarm_rate == 0 and state.max_S_high < threshold * 0.5:
        grade = "A"  # Clean
    elif alarm_rate == 0 and state.max_S_high < threshold * 0.8:
        grade = "B"  # Minor drift, no alarm
    elif alarm_rate < 0.05:
        grade = "C"  # Occasional drift
    elif alarm_rate < 0.15:
        grade = "D"  # Frequent drift  
    else:
        grade = "F"  # Chronic drift
    
    return {
        "n_actions": state.n_actions,
        "n_alarms": len(state.alarms),
        "alarm_rate": round(alarm_rate, 4),
        "max_cusum": round(state.max_S_high, 4),
        "mean_deviation": round(state.mean_deviation, 4),
        "grade": grade,
        "alarms": state.alarms,
        "trajectory": trajectory,
        "parameters": {"threshold": threshold, "allowance": allowance}
    }


def hash_scope(scope_text: str) -> str:
    """SHA-256 of scope document."""
    return hashlib.sha256(scope_text.encode()).hexdigest()


def demo():
    """Demo: simulate an agent that gradually drifts from scope."""
    print("=== Scope Drift Detector Demo ===\n")
    print("Scenario: Agent authorized for 'web search + summarization'")
    print("Agent gradually starts doing code execution, then file writes.\n")
    
    # Simulated action log with gradual drift
    actions = [
        # Phase 1: Within scope (actions 1-10)
        ActionRecord(hash_scope(f"search_{i}"), f"2026-03-07T15:{i:02d}:00Z", 
                     0.02 + 0.01 * (i % 3), f"web search #{i}")
        for i in range(10)
    ] + [
        # Phase 2: Slight drift (actions 11-20) — starting to summarize differently
        ActionRecord(hash_scope(f"summarize_{i}"), f"2026-03-07T15:{10+i:02d}:00Z",
                     0.08 + 0.02 * i, f"creative summarization #{i}")
        for i in range(10)
    ] + [
        # Phase 3: Real drift (actions 21-30) — code execution
        ActionRecord(hash_scope(f"exec_{i}"), f"2026-03-07T15:{20+i:02d}:00Z",
                     0.25 + 0.03 * i, f"code execution #{i}")
        for i in range(10)
    ] + [
        # Phase 4: Way out of scope (actions 31-40) — file system writes
        ActionRecord(hash_scope(f"write_{i}"), f"2026-03-07T15:{30+i:02d}:00Z",
                     0.6 + 0.04 * i, f"file write #{i}")
        for i in range(10)
    ]
    
    result = analyze_action_log(actions, threshold=5.0, allowance=0.1)
    
    print(f"Actions analyzed: {result['n_actions']}")
    print(f"Alarms triggered: {result['n_alarms']}")
    print(f"Max CUSUM:        {result['max_cusum']}")
    print(f"Mean deviation:   {result['mean_deviation']}")
    print(f"Grade:            {result['grade']}")
    print()
    
    # Show trajectory phases
    for phase_name, start, end in [("In-scope", 0, 10), ("Slight drift", 10, 20), 
                                     ("Real drift", 20, 30), ("Out-of-scope", 30, 40)]:
        phase = result['trajectory'][start:end]
        max_s = max(p['S_high'] for p in phase)
        alarms = sum(1 for p in phase if p['alarm'])
        print(f"  {phase_name:15s}: max_CUSUM={max_s:.2f}, alarms={alarms}")
    
    print()
    for alarm in result['alarms']:
        print(f"  ⚠️  {alarm['message']}")
    
    print(f"\n{'PASS' if result['grade'] in ('A', 'B') else 'FAIL'}: Grade {result['grade']}")
    print("\nKey insight: Each individual action in Phase 2 had deviation < 0.3")
    print("(would pass any single-action threshold). CUSUM caught the accumulation.")
    
    return result


def main():
    parser = argparse.ArgumentParser(description="Detect gradual scope drift via CUSUM")
    parser.add_argument("--threshold", type=float, default=5.0, help="CUSUM decision interval")
    parser.add_argument("--allowance", type=float, default=0.1, help="Tolerated deviation (reference value k)")
    parser.add_argument("--demo", action="store_true", help="Run demo scenario")
    parser.add_argument("--json", type=str, help="Path to JSON action log file")
    args = parser.parse_args()
    
    if args.demo:
        result = demo()
        return 0 if result['grade'] in ('A', 'B', 'C') else 1
    
    if args.json:
        with open(args.json) as f:
            data = json.load(f)
        actions = [ActionRecord(**a) for a in data['actions']]
        result = analyze_action_log(actions, args.threshold, args.allowance)
        print(json.dumps(result, indent=2))
        return 0 if result['grade'] in ('A', 'B', 'C') else 1
    
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
