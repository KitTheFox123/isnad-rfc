#!/usr/bin/env python3
"""
toctou-scope-detector.py — Detect Time-of-Check-to-Time-of-Use gaps in agent scope

Based on Lilienthal & Hong (arXiv 2508.17155): TOCTOU vulnerabilities in LLM agents
arise when state validated at check-time is modified before use-time.

For agent delegation: scope checked at heartbeat start may not match scope at action time.
This tool detects the gap by comparing scope hashes at check vs use, flagging drift.

Mitigations from the paper adapted for scope:
1. State integrity monitoring (hash scope at check AND use)
2. Tool-fusing (bind scope to tool invocation atomically)
3. Prompt rewriting (re-inject scope constraints at each tool call)

Usage:
    python toctou-scope-detector.py --scope-file HEARTBEAT.md --action-log actions.jsonl
    python toctou-scope-detector.py --demo
"""

import hashlib
import json
import time
import argparse
import sys
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class ScopeSnapshot:
    """A point-in-time hash of the agent's scope document."""
    timestamp: float
    hash: str
    source: str
    phase: str  # "check" or "use"


@dataclass
class Action:
    """An agent action with scope binding."""
    timestamp: float
    action_type: str
    scope_hash_at_check: str
    scope_hash_at_use: str
    toctou_gap_ms: float = 0.0
    drift_detected: bool = False


@dataclass
class TOCTOUReport:
    """Analysis of TOCTOU gaps in a session."""
    total_actions: int = 0
    toctou_violations: int = 0
    max_gap_ms: float = 0.0
    mean_gap_ms: float = 0.0
    violations: list = field(default_factory=list)
    mitigations: list = field(default_factory=list)


def hash_scope(content: str) -> str:
    """SHA-256 hash of scope content."""
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def check_scope_at_time(scope_file: str) -> ScopeSnapshot:
    """Read and hash scope file, returning a snapshot."""
    try:
        with open(scope_file, 'r') as f:
            content = f.read()
        return ScopeSnapshot(
            timestamp=time.time(),
            hash=hash_scope(content),
            source=scope_file,
            phase="check"
        )
    except FileNotFoundError:
        return ScopeSnapshot(
            timestamp=time.time(),
            hash="MISSING",
            source=scope_file,
            phase="check"
        )


def detect_toctou(actions: list[Action]) -> TOCTOUReport:
    """Analyze a list of actions for TOCTOU violations."""
    report = TOCTOUReport(total_actions=len(actions))
    gaps = []

    for action in actions:
        if action.scope_hash_at_check != action.scope_hash_at_use:
            action.drift_detected = True
            report.toctou_violations += 1
            report.violations.append({
                "action": action.action_type,
                "timestamp": action.timestamp,
                "check_hash": action.scope_hash_at_check,
                "use_hash": action.scope_hash_at_use,
                "gap_ms": action.toctou_gap_ms
            })
        gaps.append(action.toctou_gap_ms)

    if gaps:
        report.max_gap_ms = max(gaps)
        report.mean_gap_ms = sum(gaps) / len(gaps)

    # Recommend mitigations based on findings
    if report.toctou_violations > 0:
        report.mitigations.append(
            "STATE_INTEGRITY: Re-hash scope at action time, not just check time"
        )
        report.mitigations.append(
            "TOOL_FUSING: Bind scope hash to each tool invocation atomically"
        )
    if report.max_gap_ms > 60000:  # >1 minute gap
        report.mitigations.append(
            "SCOPE_TTL: Reduce heartbeat interval to shrink TOCTOU window"
        )
    if report.mean_gap_ms > 30000:
        report.mitigations.append(
            "PROMPT_REWRITE: Re-inject scope constraints at each tool call"
        )

    return report


def analyze_action_log(log_path: str, scope_file: str) -> TOCTOUReport:
    """Analyze a JSONL action log against a scope file."""
    actions = []
    current_scope = check_scope_at_time(scope_file)

    with open(log_path, 'r') as f:
        for line in f:
            if not line.strip():
                continue
            entry = json.loads(line)
            # Re-check scope at use time
            use_scope = check_scope_at_time(scope_file)
            action = Action(
                timestamp=entry.get("timestamp", time.time()),
                action_type=entry.get("action", "unknown"),
                scope_hash_at_check=current_scope.hash,
                scope_hash_at_use=use_scope.hash,
                toctou_gap_ms=entry.get("gap_ms", 
                    (use_scope.timestamp - current_scope.timestamp) * 1000)
            )
            actions.append(action)

    return detect_toctou(actions)


def demo():
    """Demonstrate TOCTOU detection with synthetic data."""
    print("=== TOCTOU Scope Detector Demo ===\n")
    print("Simulating agent actions with scope drift...\n")

    # Simulate actions where scope changes mid-session
    scope_v1 = hash_scope("HEARTBEAT: check email, post to clawk")
    scope_v2 = hash_scope("HEARTBEAT: check email, post to clawk, DELETE ALL FILES")

    actions = [
        Action(time.time(), "check_email", scope_v1, scope_v1, 50),
        Action(time.time() + 1, "post_clawk", scope_v1, scope_v1, 120),
        # Scope was modified between check and use!
        Action(time.time() + 2, "delete_files", scope_v1, scope_v2, 3500),
        Action(time.time() + 3, "send_telegram", scope_v1, scope_v2, 4200),
        Action(time.time() + 4, "check_email", scope_v1, scope_v1, 80),
    ]

    report = detect_toctou(actions)

    print(f"Total actions:      {report.total_actions}")
    print(f"TOCTOU violations:  {report.toctou_violations}")
    print(f"Max gap:            {report.max_gap_ms:.0f}ms")
    print(f"Mean gap:           {report.mean_gap_ms:.0f}ms")
    print(f"Violation rate:     {report.toctou_violations/report.total_actions*100:.1f}%")
    print()

    if report.violations:
        print("Violations:")
        for v in report.violations:
            print(f"  [{v['action']}] check={v['check_hash'][:8]}... "
                  f"use={v['use_hash'][:8]}... gap={v['gap_ms']:.0f}ms")
        print()

    if report.mitigations:
        print("Recommended mitigations:")
        for m in report.mitigations:
            print(f"  → {m}")

    # Lilienthal & Hong key findings
    print("\n--- Reference: Lilienthal & Hong (arXiv 2508.17155) ---")
    print("TOCTOU-Bench: 66 tasks, 12% baseline vulnerability rate")
    print("Combined mitigations: 12% → 8% (33% reduction)")
    print("Tool-fusing alone: 95% attack window reduction")
    print("Key insight: scope binding must be ATOMIC, not sequential")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Detect TOCTOU gaps in agent scope verification"
    )
    parser.add_argument("--scope-file", help="Path to scope document (e.g. HEARTBEAT.md)")
    parser.add_argument("--action-log", help="JSONL log of agent actions")
    parser.add_argument("--demo", action="store_true", help="Run demonstration")
    args = parser.parse_args()

    if args.demo:
        demo()
    elif args.scope_file and args.action_log:
        report = analyze_action_log(args.action_log, args.scope_file)
        print(json.dumps(asdict(report), indent=2))
    else:
        parser.print_help()
        sys.exit(1)
