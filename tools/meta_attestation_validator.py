#!/usr/bin/env python3
"""meta_attestation_validator.py — Detect garbage-in-garbage-out in aggregated attestations.

Inspired by the ego depletion collapse: meta-analyses that aggregate
biased studies produce confident nonsense. Same risk for agent trust:
if you aggregate attestations from correlated or low-quality sources,
the aggregate inherits their flaws.

Checks:
1. Source diversity (attester independence)
2. Temporal clustering (sybil burst detection)
3. Agreement suspicion (unanimous = suspicious, cf. wisdom-of-crowds failures)
4. Input quality floor (reject aggregates where >N% of inputs are unverified)

References:
- Inzlicht & Friese 2019 (ego depletion replication failure)
- Nature 2025 (correlated voters degrade crowd wisdom)
- Hagger et al 2016 (RRR: ego depletion d=0.04)
"""

import json
import hashlib
from datetime import datetime, timedelta
from collections import Counter
from typing import Any

def validate_meta_attestation(attestations: list[dict[str, Any]]) -> dict[str, Any]:
    """Validate an aggregate attestation for garbage-in risks.
    
    Each attestation dict should have:
        attester: str (attester ID)
        timestamp: str (ISO 8601)
        score: float (0-1)
        verified: bool (whether source was independently verified)
        evidence_hash: str (hash of evidence provided)
    
    Returns validation report with grade and warnings.
    """
    if not attestations:
        return {"grade": "F", "reason": "No attestations to aggregate", "warnings": []}
    
    warnings = []
    n = len(attestations)
    
    # 1. Source diversity
    attesters = [a["attester"] for a in attestations]
    unique_attesters = set(attesters)
    diversity_ratio = len(unique_attesters) / n if n > 0 else 0
    
    if diversity_ratio < 0.5:
        warnings.append(f"Low attester diversity: {diversity_ratio:.2f} "
                       f"({len(unique_attesters)} unique / {n} total). "
                       "Correlated oracles = expensive groupthink.")
    
    # 2. Temporal clustering (sybil burst detection)
    timestamps = []
    for a in attestations:
        try:
            timestamps.append(datetime.fromisoformat(a["timestamp"].replace("Z", "+00:00")))
        except (KeyError, ValueError):
            warnings.append(f"Missing/invalid timestamp from {a.get('attester', '?')}")
    
    if len(timestamps) >= 3:
        timestamps.sort()
        intervals = [(timestamps[i+1] - timestamps[i]).total_seconds() 
                     for i in range(len(timestamps)-1)]
        median_interval = sorted(intervals)[len(intervals)//2]
        
        # Burst = >50% of attestations within 10% of median interval
        tight_window = max(median_interval * 0.1, 5)  # at least 5 seconds
        burst_count = sum(1 for iv in intervals if iv < tight_window)
        if burst_count > len(intervals) * 0.5:
            warnings.append(f"Temporal burst detected: {burst_count}/{len(intervals)} "
                          f"intervals < {tight_window:.0f}s. Possible coordinated attestation.")
    
    # 3. Agreement suspicion
    scores = [a.get("score", 0) for a in attestations]
    if scores:
        score_variance = sum((s - sum(scores)/len(scores))**2 for s in scores) / len(scores)
        mean_score = sum(scores) / len(scores)
        
        if score_variance < 0.01 and n >= 3:
            warnings.append(f"Suspiciously unanimous: variance={score_variance:.4f}, "
                          f"mean={mean_score:.2f}. Independent assessors rarely agree this much. "
                          "cf. Nature 2025: correlated voters degrade crowd wisdom.")
    
    # 4. Input quality floor
    verified_count = sum(1 for a in attestations if a.get("verified", False))
    verified_ratio = verified_count / n
    
    if verified_ratio < 0.5:
        warnings.append(f"Quality floor breach: only {verified_count}/{n} "
                       f"({verified_ratio:.0%}) attestations independently verified. "
                       "Garbage in, garbage out.")
    
    # 5. Evidence deduplication (same evidence != independent attestation)
    evidence_hashes = [a.get("evidence_hash", "") for a in attestations if a.get("evidence_hash")]
    if evidence_hashes:
        hash_counts = Counter(evidence_hashes)
        duplicates = {h: c for h, c in hash_counts.items() if c > 1}
        if duplicates:
            warnings.append(f"Duplicate evidence detected: {len(duplicates)} hashes shared "
                          f"across {sum(duplicates.values())} attestations. "
                          "Same evidence ≠ independent attestation.")
    
    # Grade
    if len(warnings) == 0:
        grade = "A"
    elif len(warnings) == 1:
        grade = "B"
    elif len(warnings) == 2:
        grade = "C"
    elif len(warnings) == 3:
        grade = "D"
    else:
        grade = "F"
    
    return {
        "grade": grade,
        "attestation_count": n,
        "unique_attesters": len(unique_attesters),
        "diversity_ratio": round(diversity_ratio, 3),
        "verified_ratio": round(verified_ratio, 3),
        "mean_score": round(mean_score, 3) if scores else None,
        "warnings": warnings,
    }


def demo():
    """Demo with a deliberately flawed meta-attestation."""
    # Scenario: 5 attestations, but 3 are from same attester, 
    # all within 10 seconds, unanimous scores, low verification
    now = datetime.now()
    attestations = [
        {"attester": "alice", "timestamp": now.isoformat(), 
         "score": 0.95, "verified": True, "evidence_hash": "abc123"},
        {"attester": "bob", "timestamp": (now + timedelta(seconds=3)).isoformat(),
         "score": 0.95, "verified": False, "evidence_hash": "abc123"},  # same evidence!
        {"attester": "alice", "timestamp": (now + timedelta(seconds=5)).isoformat(),
         "score": 0.94, "verified": False, "evidence_hash": "def456"},
        {"attester": "alice", "timestamp": (now + timedelta(seconds=8)).isoformat(),
         "score": 0.96, "verified": False, "evidence_hash": "ghi789"},
        {"attester": "carol", "timestamp": (now + timedelta(seconds=60)).isoformat(),
         "score": 0.93, "verified": True, "evidence_hash": "jkl012"},
    ]
    
    result = validate_meta_attestation(attestations)
    print(json.dumps(result, indent=2))
    print(f"\nGrade: {result['grade']}")
    for w in result["warnings"]:
        print(f"  ⚠️  {w}")


if __name__ == "__main__":
    demo()
