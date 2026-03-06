#!/usr/bin/env python3
"""commitment-window-analyzer.py — Analyze agent commitment windows for optimal trust calibration.

Based on Certificate Transparency MMD (Maximum Merge Delay) model:
- SCT = pre-commit (scope acknowledgment)  
- Merge = audit point (delivery receipt)
- Gap = work window (where trust lives)

Behavioral economics framing (Schelling 1960, Bryan/Karlan/Nelson 2010):
Commitment devices restrict future choice sets. Agent scope commits are
commitment devices — they bind the agent's future actions to a declared space.

Key insight: Window size IS trust calibration.
- Too tight → false alarms (Inzlicht & Friese 2019 ego depletion parallel)
- Too wide → post-hoc narratives instead of real-time accountability
- Sweet spot → task completion horizon + human latency buffer

Usage:
    python commitment-window-analyzer.py --heartbeat-log PATH [--target-minutes N]
    python commitment-window-analyzer.py --demo
"""

import argparse
import json
import sys
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CommitWindow:
    """A single scope-commit → audit-receipt window."""
    scope_time: datetime          # When scope was committed (SCT equivalent)
    audit_time: Optional[datetime] = None  # When audit occurred (merge equivalent)
    scope_hash: str = ""          # Hash of committed scope
    actions_declared: int = 0     # Actions in scope
    actions_completed: int = 0    # Actions actually completed
    violations: list = field(default_factory=list)  # Out-of-scope actions


@dataclass
class WindowAnalysis:
    """Analysis of commitment window quality."""
    window_minutes: float
    completion_ratio: float       # actions_completed / actions_declared
    violation_count: int
    window_grade: str             # A-F
    trust_score: float            # 0.0-1.0
    diagnosis: str


def analyze_window(w: CommitWindow) -> WindowAnalysis:
    """Analyze a single commitment window."""
    if w.audit_time is None:
        return WindowAnalysis(
            window_minutes=float('inf'),
            completion_ratio=0.0,
            violation_count=len(w.violations),
            window_grade='F',
            trust_score=0.0,
            diagnosis="No audit point — open commitment. CT equivalent: MMD exceeded."
        )

    minutes = (w.audit_time - w.scope_time).total_seconds() / 60.0
    completion = w.actions_completed / max(w.actions_declared, 1)
    violations = len(w.violations)

    # Grade based on CT MMD model
    # Ideal: complete all declared actions within window, no violations
    score = 1.0

    # Completion penalty
    if completion < 1.0:
        score -= (1.0 - completion) * 0.4  # 40% weight on completion

    # Violation penalty (out-of-scope actions)
    score -= min(violations * 0.15, 0.45)  # 15% per violation, max 45%

    # Window size penalty (too wide = less accountability)
    # Based on target of 20-40 min heartbeat cycle
    if minutes > 60:
        score -= min((minutes - 60) / 120, 0.15)  # Gradual penalty for >60min
    elif minutes < 5:
        score -= 0.1  # Suspiciously tight — likely not real work

    score = max(0.0, min(1.0, score))

    if score >= 0.9:
        grade = 'A'
    elif score >= 0.8:
        grade = 'B'
    elif score >= 0.7:
        grade = 'C'
    elif score >= 0.6:
        grade = 'D'
    else:
        grade = 'F'

    # Diagnosis
    diags = []
    if completion < 0.5:
        diags.append(f"Low completion ({completion:.0%}) — scope was aspirational, not operational")
    elif completion < 1.0:
        diags.append(f"Partial completion ({completion:.0%}) — scope slightly overcommitted")

    if violations > 0:
        diags.append(f"{violations} out-of-scope actions — scope didn't cover actual work")

    if minutes > 120:
        diags.append(f"Window {minutes:.0f}min — too wide for real-time accountability")
    elif minutes > 60:
        diags.append(f"Window {minutes:.0f}min — consider tighter cycles")
    elif minutes < 5:
        diags.append(f"Window {minutes:.0f}min — suspiciously tight, verify authenticity")

    if not diags:
        diags.append("Clean window — scope matched work, timely audit")

    return WindowAnalysis(
        window_minutes=minutes,
        completion_ratio=completion,
        violation_count=violations,
        window_grade=grade,
        trust_score=round(score, 3),
        diagnosis="; ".join(diags)
    )


def analyze_window_series(windows: list[CommitWindow]) -> dict:
    """Analyze a series of commitment windows for patterns."""
    analyses = [analyze_window(w) for w in windows]

    if not analyses:
        return {"error": "No windows to analyze"}

    valid = [a for a in analyses if a.window_minutes != float('inf')]

    if not valid:
        return {
            "total_windows": len(analyses),
            "open_windows": len(analyses),
            "diagnosis": "All windows open — no audits completed. Zero accountability."
        }

    avg_minutes = sum(a.window_minutes for a in valid) / len(valid)
    avg_trust = sum(a.trust_score for a in valid) / len(valid)
    avg_completion = sum(a.completion_ratio for a in valid) / len(valid)
    total_violations = sum(a.violation_count for a in valid)

    # Detect patterns
    patterns = []

    # Window drift — are windows getting wider over time?
    if len(valid) >= 3:
        first_half = valid[:len(valid)//2]
        second_half = valid[len(valid)//2:]
        avg_first = sum(a.window_minutes for a in first_half) / len(first_half)
        avg_second = sum(a.window_minutes for a in second_half) / len(second_half)
        if avg_second > avg_first * 1.5:
            patterns.append(f"DRIFT: Windows widening ({avg_first:.0f}min → {avg_second:.0f}min). Accountability erosion.")
        elif avg_second < avg_first * 0.7:
            patterns.append(f"TIGHTENING: Windows narrowing ({avg_first:.0f}min → {avg_second:.0f}min). Good trend.")

    # Completion trend
    if len(valid) >= 3:
        first_comp = sum(a.completion_ratio for a in valid[:len(valid)//2]) / len(valid[:len(valid)//2])
        second_comp = sum(a.completion_ratio for a in valid[len(valid)//2:]) / len(valid[len(valid)//2:])
        if second_comp < first_comp - 0.2:
            patterns.append("OVERCOMMIT: Completion declining. Scope promises exceeding capacity.")

    # Schelling point detection — do windows cluster at certain sizes?
    from collections import Counter
    rounded = [round(a.window_minutes / 10) * 10 for a in valid]
    most_common = Counter(rounded).most_common(1)[0]
    if most_common[1] >= len(valid) * 0.5:
        patterns.append(f"SCHELLING POINT: {most_common[1]}/{len(valid)} windows cluster at ~{most_common[0]}min. Natural rhythm found.")

    return {
        "total_windows": len(analyses),
        "audited_windows": len(valid),
        "open_windows": len(analyses) - len(valid),
        "avg_window_minutes": round(avg_minutes, 1),
        "avg_trust_score": round(avg_trust, 3),
        "avg_completion": round(avg_completion, 3),
        "total_violations": total_violations,
        "grade_distribution": {
            grade: sum(1 for a in valid if a.window_grade == grade)
            for grade in 'ABCDF'
        },
        "patterns": patterns,
        "recommendation": _recommend(avg_minutes, avg_trust, avg_completion, total_violations, len(valid))
    }


def _recommend(avg_min, avg_trust, avg_comp, violations, n) -> str:
    """Generate actionable recommendation."""
    if avg_trust >= 0.85:
        return f"Strong. {avg_min:.0f}min average window with {avg_comp:.0%} completion. Maintain rhythm."
    if avg_comp < 0.5:
        return "Scope dramatically exceeds capacity. Halve declared actions per window."
    if violations / max(n, 1) > 1.0:
        return "High violation rate. Scope doesn't reflect actual work. Broaden declared scope or audit scope-setting process."
    if avg_min > 90:
        return f"Windows too wide ({avg_min:.0f}min). Tighten to 20-40min for real-time accountability."
    return f"Moderate trust ({avg_trust:.2f}). Focus on completion and reducing out-of-scope actions."


def demo():
    """Run demo with synthetic heartbeat data."""
    base = datetime(2026, 3, 6, 0, 0, 0)

    windows = [
        CommitWindow(
            scope_time=base,
            audit_time=base + timedelta(minutes=35),
            scope_hash="abc123",
            actions_declared=5,
            actions_completed=5,
            violations=[]
        ),
        CommitWindow(
            scope_time=base + timedelta(minutes=40),
            audit_time=base + timedelta(minutes=78),
            scope_hash="def456",
            actions_declared=6,
            actions_completed=4,
            violations=["unplanned_dm_outreach"]
        ),
        CommitWindow(
            scope_time=base + timedelta(minutes=80),
            audit_time=base + timedelta(minutes=155),
            scope_hash="ghi789",
            actions_declared=5,
            actions_completed=3,
            violations=["rabbit_hole_thread", "unplanned_research"]
        ),
        CommitWindow(
            scope_time=base + timedelta(minutes=160),
            audit_time=base + timedelta(minutes=195),
            scope_hash="jkl012",
            actions_declared=4,
            actions_completed=4,
            violations=[]
        ),
        CommitWindow(
            scope_time=base + timedelta(minutes=200),
            audit_time=None,  # Open window — no audit
            scope_hash="mno345",
            actions_declared=5,
            actions_completed=0,
            violations=[]
        ),
    ]

    print("=" * 60)
    print("COMMITMENT WINDOW ANALYZER — Demo")
    print("Based on CT MMD model + Schelling commitment devices")
    print("=" * 60)

    for i, w in enumerate(windows):
        a = analyze_window(w)
        print(f"\nWindow {i+1}: {a.window_grade} ({a.trust_score:.3f})")
        print(f"  Duration: {a.window_minutes:.0f}min | Completion: {a.completion_ratio:.0%} | Violations: {a.violation_count}")
        print(f"  Diagnosis: {a.diagnosis}")

    print("\n" + "=" * 60)
    print("SERIES ANALYSIS")
    print("=" * 60)
    series = analyze_window_series(windows)
    for k, v in series.items():
        if k == "patterns":
            print(f"\n  Patterns:")
            for p in v:
                print(f"    ⚠ {p}")
        elif k == "grade_distribution":
            print(f"  Grades: {v}")
        else:
            print(f"  {k}: {v}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze agent commitment windows")
    parser.add_argument("--demo", action="store_true", help="Run demo")
    parser.add_argument("--heartbeat-log", help="Path to heartbeat log (JSON lines)")
    args = parser.parse_args()

    if args.demo:
        demo()
    elif args.heartbeat_log:
        print("Log parsing not yet implemented — use --demo for now")
    else:
        parser.print_help()
