#!/usr/bin/env python3
"""
attestation_loafing_detector.py — Detect social loafing in multi-agent attestation

Based on Ringelmann (1913) and Karau & Williams (1993) CEM:
- More attesters → less individual verification effort
- Identifiable contributions reduce loafing
- Correlated attestations suggest rubber-stamping

Detects:
1. Temporal clustering (all sign within seconds = no independent review)
2. Score uniformity (identical scores = no independent evaluation)
3. Effort decay (later attesters copy earlier ones)
4. Free riding (attester always agrees with majority)

Tool #14 for isnad-rfc.
"""

import json
import math
import statistics
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Attestation:
    attester_id: str
    timestamp: float  # unix epoch
    score: float  # 0.0 - 1.0
    comment_length: int = 0  # proxy for effort
    agrees_with_majority: bool = True


@dataclass
class LoafingReport:
    temporal_clustering: float = 0.0  # 0-1, higher = more clustered
    score_uniformity: float = 0.0  # 0-1, higher = more uniform
    effort_decay: float = 0.0  # 0-1, higher = more decay over sequence
    free_rider_ids: list = field(default_factory=list)
    ringelmann_ratio: float = 1.0  # actual/potential effort
    grade: str = "?"
    details: dict = field(default_factory=dict)


def detect_temporal_clustering(attestations: list[Attestation], threshold_seconds: float = 30.0) -> float:
    """Attestations within threshold_seconds suggest no independent review."""
    if len(attestations) < 2:
        return 0.0
    sorted_atts = sorted(attestations, key=lambda a: a.timestamp)
    gaps = [sorted_atts[i+1].timestamp - sorted_atts[i].timestamp for i in range(len(sorted_atts)-1)]
    if not gaps:
        return 0.0
    # Fraction of gaps below threshold
    clustered = sum(1 for g in gaps if g < threshold_seconds) / len(gaps)
    return clustered


def detect_score_uniformity(attestations: list[Attestation]) -> float:
    """Identical or near-identical scores suggest rubber-stamping."""
    if len(attestations) < 2:
        return 0.0
    scores = [a.score for a in attestations]
    if max(scores) == min(scores):
        return 1.0
    cv = statistics.stdev(scores) / statistics.mean(scores) if statistics.mean(scores) > 0 else 0
    # Low CV = high uniformity. Map CV 0-0.3 to uniformity 1.0-0.0
    uniformity = max(0.0, 1.0 - cv / 0.3)
    return uniformity


def detect_effort_decay(attestations: list[Attestation]) -> float:
    """Later attesters put in less effort (shorter comments) than earlier ones."""
    if len(attestations) < 3:
        return 0.0
    sorted_atts = sorted(attestations, key=lambda a: a.timestamp)
    efforts = [a.comment_length for a in sorted_atts]
    if efforts[0] == 0:
        return 0.0
    # Compare first half vs second half average effort
    mid = len(efforts) // 2
    first_half = statistics.mean(efforts[:mid]) if efforts[:mid] else 0
    second_half = statistics.mean(efforts[mid:]) if efforts[mid:] else 0
    if first_half == 0:
        return 0.0
    decay = max(0.0, (first_half - second_half) / first_half)
    return decay


def detect_free_riders(attester_history: dict[str, list[bool]], threshold: float = 0.95) -> list[str]:
    """Attesters who agree with majority >threshold of the time are free riders."""
    free_riders = []
    for attester_id, agreements in attester_history.items():
        if len(agreements) < 5:
            continue
        agreement_rate = sum(agreements) / len(agreements)
        if agreement_rate >= threshold:
            free_riders.append(attester_id)
    return free_riders


def compute_ringelmann_ratio(attestations: list[Attestation], solo_effort: float = 100.0) -> float:
    """Ratio of actual group effort to potential (sum of individual maxima).
    
    Ringelmann found: 2 people = 93%, 3 = 85%, 8 = 49%.
    We use comment_length as effort proxy.
    """
    if not attestations:
        return 1.0
    n = len(attestations)
    actual_total = sum(a.comment_length for a in attestations)
    potential_total = n * solo_effort
    if potential_total == 0:
        return 1.0
    return actual_total / potential_total


def analyze(attestations: list[Attestation], 
            attester_history: Optional[dict[str, list[bool]]] = None,
            solo_effort: float = 100.0) -> LoafingReport:
    """Full social loafing analysis on a set of attestations."""
    report = LoafingReport()
    
    report.temporal_clustering = detect_temporal_clustering(attestations)
    report.score_uniformity = detect_score_uniformity(attestations)
    report.effort_decay = detect_effort_decay(attestations)
    report.ringelmann_ratio = compute_ringelmann_ratio(attestations, solo_effort)
    
    if attester_history:
        report.free_rider_ids = detect_free_riders(attester_history)
    
    # Composite score (0 = no loafing, 1 = maximum loafing)
    composite = (
        report.temporal_clustering * 0.3 +
        report.score_uniformity * 0.25 +
        report.effort_decay * 0.25 +
        (1.0 - report.ringelmann_ratio) * 0.2
    )
    
    # Grade
    if composite < 0.15:
        report.grade = "A"  # Independent verification
    elif composite < 0.30:
        report.grade = "B"  # Mild loafing
    elif composite < 0.50:
        report.grade = "C"  # Moderate loafing
    elif composite < 0.70:
        report.grade = "D"  # Significant loafing
    else:
        report.grade = "F"  # Rubber-stamping
    
    report.details = {
        "n_attesters": len(attestations),
        "composite_score": round(composite, 3),
        "temporal_clustering": round(report.temporal_clustering, 3),
        "score_uniformity": round(report.score_uniformity, 3),
        "effort_decay": round(report.effort_decay, 3),
        "ringelmann_ratio": round(report.ringelmann_ratio, 3),
        "free_riders": report.free_rider_ids,
        "grade": report.grade,
        "ringelmann_1913": f"{len(attestations)} attesters at {report.ringelmann_ratio:.0%} of potential (Ringelmann predicted {max(0, 100 - 7*len(attestations)):.0f}%)"
    }
    
    return report


def demo():
    """Demo: good attestation group vs rubber-stamp group."""
    import time
    
    print("=== Attestation Loafing Detector ===\n")
    
    # Good group: staggered timing, varied scores, substantial comments
    good = [
        Attestation("alice", 1000, 0.85, comment_length=150),
        Attestation("bob", 1300, 0.72, comment_length=120),  # 5 min later
        Attestation("carol", 1800, 0.91, comment_length=180),  # 8 min later
    ]
    
    report1 = analyze(good, solo_effort=150)
    print("Good attestation group:")
    print(json.dumps(report1.details, indent=2))
    
    print()
    
    # Rubber-stamp group: all sign within 10s, identical scores, declining effort
    bad = [
        Attestation("agent1", 1000, 0.90, comment_length=100),
        Attestation("agent2", 1005, 0.90, comment_length=40),
        Attestation("agent3", 1008, 0.90, comment_length=15),
        Attestation("agent4", 1010, 0.90, comment_length=8),
        Attestation("agent5", 1012, 0.90, comment_length=5),
    ]
    
    history = {
        "agent2": [True]*20,
        "agent4": [True]*18 + [False]*2,
        "agent5": [True]*19 + [False]*1,
    }
    
    report2 = analyze(bad, attester_history=history, solo_effort=100)
    print("Rubber-stamp group:")
    print(json.dumps(report2.details, indent=2))


if __name__ == "__main__":
    demo()
