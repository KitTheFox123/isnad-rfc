#!/usr/bin/env python3
"""repetition_truth_detector.py — Detect illusory truth patterns in attestation networks.

Based on Hassan & Barber (2021): perceived truth increases logarithmically with
repetition. First independent verification = biggest signal (d=1.0). After ~9
repetitions, gains plateau. Correlated attesters add noise, not signal.

Detects:
1. Rubber-stamp patterns (high similarity, low diversity)
2. Echo chamber attestations (same source repeated)
3. Diminishing returns (marginal value of Nth attester)
4. Optimal attester count recommendation

Reference: Hassan & Barber (2021) Cogn Res Princ Implic 6:38
"""

import json
import math
import sys
from collections import Counter
from dataclasses import dataclass
from typing import Optional


@dataclass
class Attestation:
    attester_id: str
    claim_hash: str
    score: float  # 0-1
    timestamp: float
    source_model: Optional[str] = None
    source_operator: Optional[str] = None


@dataclass
class TruthInflationReport:
    claim_hash: str
    n_attestations: int
    n_unique_sources: int
    diversity_score: float  # 0-1, higher = more diverse
    marginal_value_last: float  # marginal truth-value of last attester
    optimal_n: int  # recommended attester count
    rubber_stamp_score: float  # 0-1, higher = more rubber-stamping
    grade: str  # A-F
    details: list[str]


def compute_diversity(attestations: list[Attestation]) -> float:
    """Diversity based on unique operators and models."""
    operators = set()
    models = set()
    for a in attestations:
        if a.source_operator:
            operators.add(a.source_operator)
        if a.source_model:
            models.add(a.source_model)

    n = len(attestations)
    if n <= 1:
        return 0.0

    # Shannon entropy normalized
    op_counts = Counter(a.source_operator for a in attestations if a.source_operator)
    if not op_counts:
        return 0.0

    total = sum(op_counts.values())
    entropy = -sum((c / total) * math.log2(c / total) for c in op_counts.values() if c > 0)
    max_entropy = math.log2(len(op_counts)) if len(op_counts) > 1 else 1.0

    return entropy / max_entropy if max_entropy > 0 else 0.0


def marginal_truth_value(n: int) -> float:
    """Hassan & Barber logarithmic model: truth gain from Nth attestation.

    Biggest jump = 1st→2nd (d≈1.0). After 9, practically zero.
    """
    if n <= 1:
        return 1.0  # first attestation = full value
    # Logarithmic: gain = log(n+1) - log(n)
    return math.log(n + 1) - math.log(n)


def rubber_stamp_score(attestations: list[Attestation]) -> float:
    """Detect rubber-stamping: high score uniformity + temporal clustering."""
    if len(attestations) < 2:
        return 0.0

    scores = [a.score for a in attestations]
    mean_score = sum(scores) / len(scores)
    variance = sum((s - mean_score) ** 2 for s in scores) / len(scores)

    # Low variance in scores = rubber stamp signal
    # Variance of 0 = perfect rubber stamp, variance > 0.1 = genuine
    uniformity = max(0, 1.0 - variance * 10)

    # Temporal clustering: all within short window
    timestamps = sorted(a.timestamp for a in attestations)
    if len(timestamps) >= 2:
        span = timestamps[-1] - timestamps[0]
        # If all attestations within 60 seconds, suspicious
        temporal = max(0, 1.0 - span / 3600) if span < 3600 else 0.0
    else:
        temporal = 0.0

    return 0.6 * uniformity + 0.4 * temporal


def analyze_claim(attestations: list[Attestation]) -> TruthInflationReport:
    """Analyze attestation set for illusory truth patterns."""
    n = len(attestations)
    claim_hash = attestations[0].claim_hash if attestations else "unknown"

    diversity = compute_diversity(attestations)
    rubber = rubber_stamp_score(attestations)

    # Marginal value of last attester
    mv_last = marginal_truth_value(n)

    # Optimal N: where marginal value drops below 0.1
    optimal_n = 1
    for i in range(1, 50):
        if marginal_truth_value(i) < 0.1:
            optimal_n = i - 1
            break
    else:
        optimal_n = 50

    details = []

    # Grade
    composite = (1 - rubber) * 0.4 + diversity * 0.4 + min(mv_last * 5, 1.0) * 0.2

    if composite >= 0.8:
        grade = "A"
    elif composite >= 0.6:
        grade = "B"
    elif composite >= 0.4:
        grade = "C"
    elif composite >= 0.2:
        grade = "D"
    else:
        grade = "F"

    # Diagnostics
    if rubber > 0.7:
        details.append(f"⚠️ High rubber-stamp score ({rubber:.2f}): attesters may not be independently evaluating")
    if diversity < 0.3:
        details.append(f"⚠️ Low diversity ({diversity:.2f}): attesters too similar (same operator/model)")
    if n > optimal_n:
        details.append(f"📉 Diminishing returns: {n} attesters but optimal is ~{optimal_n}. Extra attesters add noise.")
    if mv_last < 0.05:
        details.append(f"📉 Marginal value of attester #{n} = {mv_last:.3f} (near zero)")
    if n <= 3 and diversity > 0.5:
        details.append(f"✅ Small diverse set: {n} independent attesters is strong (Hassan & Barber: first repeat = biggest signal)")

    return TruthInflationReport(
        claim_hash=claim_hash,
        n_attestations=n,
        n_unique_sources=len(set(a.source_operator for a in attestations if a.source_operator)),
        diversity_score=diversity,
        marginal_value_last=mv_last,
        optimal_n=optimal_n,
        rubber_stamp_score=rubber,
        grade=grade,
        details=details,
    )


def demo():
    """Demo with synthetic attestation data."""
    import time

    now = time.time()

    # Good: 3 diverse attesters
    good = [
        Attestation("alice", "claim_001", 0.85, now, "opus", "operator_a"),
        Attestation("bob", "claim_001", 0.72, now + 3600, "sonnet", "operator_b"),
        Attestation("carol", "claim_001", 0.91, now + 7200, "gpt4", "operator_c"),
    ]

    # Bad: 8 rubber stamps from same operator
    bad = [
        Attestation(f"bot_{i}", "claim_002", 0.95, now + i * 5, "sonnet", "operator_x")
        for i in range(8)
    ]

    print("=" * 60)
    print("REPETITION TRUTH DETECTOR")
    print("Based on Hassan & Barber (2021)")
    print("=" * 60)

    for label, attestations in [("Good (3 diverse)", good), ("Bad (8 rubber stamps)", bad)]:
        report = analyze_claim(attestations)
        print(f"\n--- {label} ---")
        print(f"  Claim: {report.claim_hash}")
        print(f"  Attestations: {report.n_attestations} ({report.n_unique_sources} unique sources)")
        print(f"  Diversity: {report.diversity_score:.2f}")
        print(f"  Rubber-stamp: {report.rubber_stamp_score:.2f}")
        print(f"  Marginal value of last: {report.marginal_value_last:.3f}")
        print(f"  Optimal N: {report.optimal_n}")
        print(f"  Grade: {report.grade}")
        for d in report.details:
            print(f"  {d}")

    # Marginal value curve
    print(f"\n--- Marginal Value Curve (Hassan & Barber logarithmic model) ---")
    for n in [1, 2, 3, 5, 9, 15, 27]:
        mv = marginal_truth_value(n)
        bar = "█" * int(mv * 40)
        print(f"  Attester #{n:2d}: {mv:.3f} {bar}")


if __name__ == "__main__":
    demo()
