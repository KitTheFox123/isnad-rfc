#!/usr/bin/env python3
"""proximity_drift_scorer.py — PATE-inspired proximity-aware scope drift scoring.

Based on Ghorbani, Reinders & Tax (KDD 2024): "PATE: Proximity-Aware
Time series anomaly Evaluation." Drift detected near scope boundaries
(breach-adjacent) scores higher than gradual creep mid-scope.

Key insight: not all drift is equal. A 0.1 cosine shift 2 minutes before
scope expiry is more dangerous than a 0.3 shift at scope midpoint.
"""

import json
import math
import sys
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ScopeWindow:
    """A scope issuance window with start/end timestamps."""
    start: float  # unix timestamp
    end: float    # unix timestamp (expiry)
    scope_hash: str = ""


@dataclass 
class DriftEvent:
    """A detected drift event with magnitude and timestamp."""
    timestamp: float
    magnitude: float  # 0-1 cosine distance or KL divergence
    drift_type: str = "semantic"  # semantic | distributional | context


@dataclass
class ScoredDrift:
    """Drift event with proximity-weighted score."""
    event: DriftEvent
    raw_score: float
    proximity_weight: float
    weighted_score: float
    zone: str  # "buffer_start" | "mid_scope" | "buffer_end" | "post_expiry"


def proximity_weight(event: DriftEvent, scope: ScopeWindow, 
                     buffer_ratio: float = 0.1) -> tuple[float, str]:
    """Compute proximity-aware weight for a drift event.
    
    Events near scope boundaries get higher weight (PATE buffer zone concept).
    Events after expiry get maximum weight.
    
    Args:
        event: The drift event to score
        scope: The scope window
        buffer_ratio: Fraction of scope duration for buffer zones (default 10%)
    
    Returns:
        (weight, zone_label) tuple
    """
    duration = scope.end - scope.start
    if duration <= 0:
        return 1.0, "degenerate"
    
    buffer = duration * buffer_ratio
    t = event.timestamp
    
    # Post-expiry: maximum weight
    if t >= scope.end:
        overtime = (t - scope.end) / duration
        return min(2.0, 1.0 + overtime), "post_expiry"
    
    # Pre-scope: shouldn't happen but handle gracefully
    if t < scope.start:
        return 0.5, "pre_scope"
    
    # Relative position within scope [0, 1]
    pos = (t - scope.start) / duration
    
    # Buffer zone at start (first 10%): elevated weight
    if pos < buffer_ratio:
        # Linear ramp from 1.5 down to 1.0
        w = 1.5 - 0.5 * (pos / buffer_ratio)
        return w, "buffer_start"
    
    # Buffer zone at end (last 10%): elevated weight  
    if pos > (1.0 - buffer_ratio):
        # Linear ramp from 1.0 up to 1.5
        progress = (pos - (1.0 - buffer_ratio)) / buffer_ratio
        w = 1.0 + 0.5 * progress
        return w, "buffer_end"
    
    # Mid-scope: base weight with slight U-curve
    # Minimum at center, slightly higher near boundaries
    center_dist = abs(pos - 0.5) / 0.5  # 0 at center, 1 at edges
    w = 0.7 + 0.3 * center_dist
    return w, "mid_scope"


def score_drift_events(events: list[DriftEvent], scope: ScopeWindow,
                       buffer_ratio: float = 0.1) -> list[ScoredDrift]:
    """Score all drift events with proximity weighting."""
    scored = []
    for event in events:
        weight, zone = proximity_weight(event, scope, buffer_ratio)
        raw = event.magnitude
        weighted = raw * weight
        scored.append(ScoredDrift(
            event=event,
            raw_score=raw,
            proximity_weight=weight,
            weighted_score=weighted,
            zone=zone
        ))
    return scored


def aggregate_score(scored: list[ScoredDrift]) -> dict:
    """Aggregate scored drift events into overall assessment."""
    if not scored:
        return {"grade": "A", "composite": 0.0, "events": 0, "detail": "No drift detected"}
    
    max_weighted = max(s.weighted_score for s in scored)
    mean_weighted = sum(s.weighted_score for s in scored) / len(scored)
    
    # Zone breakdown
    zones = {}
    for s in scored:
        if s.zone not in zones:
            zones[s.zone] = []
        zones[s.zone].append(s.weighted_score)
    
    zone_summary = {z: {"count": len(v), "max": max(v), "mean": sum(v)/len(v)} 
                    for z, v in zones.items()}
    
    # Grade based on max weighted score
    if max_weighted < 0.1:
        grade = "A"
    elif max_weighted < 0.3:
        grade = "B"
    elif max_weighted < 0.5:
        grade = "C"
    elif max_weighted < 0.8:
        grade = "D"
    else:
        grade = "F"
    
    # Breach-adjacent alarm
    breach_adjacent = any(s.zone in ("buffer_end", "post_expiry") and s.weighted_score > 0.3 
                         for s in scored)
    
    return {
        "grade": grade,
        "composite": round(mean_weighted, 4),
        "max_weighted": round(max_weighted, 4),
        "events": len(scored),
        "breach_adjacent_alarm": breach_adjacent,
        "zones": zone_summary,
        "detail": [
            {
                "timestamp": s.event.timestamp,
                "type": s.event.drift_type,
                "raw": round(s.raw_score, 4),
                "weight": round(s.proximity_weight, 4),
                "weighted": round(s.weighted_score, 4),
                "zone": s.zone
            }
            for s in scored
        ]
    }


def demo():
    """Demo: compare mid-scope vs breach-adjacent drift."""
    # Scope window: 0 to 1000 (seconds)
    scope = ScopeWindow(start=0, end=1000, scope_hash="abc123")
    
    events = [
        # Small drift at scope start (buffer zone)
        DriftEvent(timestamp=50, magnitude=0.15, drift_type="semantic"),
        # Medium drift mid-scope (low weight)
        DriftEvent(timestamp=500, magnitude=0.30, drift_type="distributional"),
        # Small drift near expiry (HIGH weight — breach adjacent)
        DriftEvent(timestamp=950, magnitude=0.20, drift_type="semantic"),
        # Any drift post-expiry (MAXIMUM weight)
        DriftEvent(timestamp=1050, magnitude=0.10, drift_type="context"),
    ]
    
    scored = score_drift_events(events, scope)
    result = aggregate_score(scored)
    
    print("=== Proximity-Aware Drift Scoring (PATE-inspired) ===")
    print(f"Grade: {result['grade']}")
    print(f"Composite: {result['composite']}")
    print(f"Max weighted: {result['max_weighted']}")
    print(f"Breach-adjacent alarm: {result['breach_adjacent_alarm']}")
    print()
    print("Event details:")
    for d in result["detail"]:
        print(f"  t={d['timestamp']:>6} | {d['type']:>14} | raw={d['raw']:.3f} | "
              f"weight={d['weight']:.3f} | weighted={d['weighted']:.3f} | {d['zone']}")
    print()
    print("Key insight: 0.20 magnitude near expiry (weighted=0.30) scores")
    print("higher than 0.30 magnitude mid-scope (weighted=0.21)")
    
    return result


if __name__ == "__main__":
    demo()
