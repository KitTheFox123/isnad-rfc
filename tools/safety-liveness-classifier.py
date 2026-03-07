#!/usr/bin/env python3
"""
safety-liveness-classifier.py — Classify agent accountability properties
as safety ("bad things don't happen") or liveness ("good things do happen").

Based on Lamport 1977 / Alpern & Schneider 1985 decomposition.
Every correctness property = conjunction of safety + liveness.

For isnad: heartbeats = liveness proofs, scope-commits = safety properties.
Different verification methods required for each.

Usage:
    python safety-liveness-classifier.py [--heartbeat-log FILE] [--scope-log FILE]
"""

import argparse
import json
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class PropertyType(Enum):
    SAFETY = "safety"       # Bad things don't happen (scope violations)
    LIVENESS = "liveness"   # Good things do happen (heartbeats, responses)
    MIXED = "mixed"         # Conjunction of both


@dataclass
class AccountabilityProperty:
    name: str
    property_type: PropertyType
    description: str
    verification_method: str
    evidence: Optional[str] = None


@dataclass
class AgentProfile:
    agent_id: str
    safety_violations: int = 0
    liveness_failures: int = 0
    total_heartbeats: int = 0
    total_scope_checks: int = 0
    safety_score: float = 1.0   # 1.0 = perfect safety
    liveness_score: float = 1.0  # 1.0 = perfect liveness

    @property
    def total_correctness(self) -> float:
        """Lamport: total correctness = safety AND liveness."""
        return self.safety_score * self.liveness_score

    @property
    def reputation_gap(self) -> float:
        """The gap between safety and liveness is where reputation lives."""
        return abs(self.safety_score - self.liveness_score)


# Canonical accountability properties for agent systems
CANONICAL_PROPERTIES = [
    AccountabilityProperty(
        name="scope_adherence",
        property_type=PropertyType.SAFETY,
        description="Agent never acts outside declared scope",
        verification_method="Scope-commit log + action audit trail",
    ),
    AccountabilityProperty(
        name="no_unauthorized_delegation",
        property_type=PropertyType.SAFETY,
        description="Agent never delegates to unauthorized sub-agents",
        verification_method="Delegation chain verification (isnad)",
    ),
    AccountabilityProperty(
        name="heartbeat_liveness",
        property_type=PropertyType.LIVENESS,
        description="Agent produces heartbeats within TTL window",
        verification_method="Heartbeat monitor with decay function",
    ),
    AccountabilityProperty(
        name="response_liveness",
        property_type=PropertyType.LIVENESS,
        description="Agent responds to queries within SLA",
        verification_method="Request-response latency tracking",
    ),
    AccountabilityProperty(
        name="transparency_log_inclusion",
        property_type=PropertyType.MIXED,
        description="Every action is logged (liveness) and log is append-only (safety)",
        verification_method="CT-style Merkle tree with consistency proofs",
    ),
    AccountabilityProperty(
        name="credential_freshness",
        property_type=PropertyType.SAFETY,
        description="Agent never uses expired credentials",
        verification_method="Short-lived cert TTL check",
    ),
    AccountabilityProperty(
        name="attestation_reciprocity",
        property_type=PropertyType.LIVENESS,
        description="Agent attests peers who attest it (reciprocal trust)",
        verification_method="Attestation graph analysis",
    ),
    AccountabilityProperty(
        name="silence_detection",
        property_type=PropertyType.MIXED,
        description="Omissions are detected (liveness) and flagged (safety)",
        verification_method="Selection gap detector + silence monitor",
    ),
]


def classify_heartbeat_log(log_entries: list[dict], ttl_seconds: float = 7200) -> AgentProfile:
    """Analyze heartbeat log for liveness properties."""
    profile = AgentProfile(agent_id="self")
    profile.total_heartbeats = len(log_entries)

    if len(log_entries) < 2:
        return profile

    gaps = []
    for i in range(1, len(log_entries)):
        prev_ts = log_entries[i - 1].get("timestamp", 0)
        curr_ts = log_entries[i].get("timestamp", 0)
        gap = curr_ts - prev_ts
        gaps.append(gap)
        if gap > ttl_seconds:
            profile.liveness_failures += 1

    if gaps:
        profile.liveness_score = max(0, 1.0 - (profile.liveness_failures / len(gaps)))

    return profile


def classify_scope_log(scope_entries: list[dict]) -> AgentProfile:
    """Analyze scope log for safety properties."""
    profile = AgentProfile(agent_id="self")
    profile.total_scope_checks = len(scope_entries)

    for entry in scope_entries:
        if entry.get("out_of_scope", False):
            profile.safety_violations += 1

    if scope_entries:
        profile.safety_score = max(0, 1.0 - (profile.safety_violations / len(scope_entries)))

    return profile


def print_classification_report(profile: AgentProfile):
    """Print Lamport-style classification report."""
    print("=" * 60)
    print("SAFETY/LIVENESS CLASSIFICATION REPORT")
    print("=" * 60)
    print(f"\nAgent: {profile.agent_id}")
    print(f"\n--- Safety (bad things don't happen) ---")
    print(f"  Scope checks:     {profile.total_scope_checks}")
    print(f"  Violations:       {profile.safety_violations}")
    print(f"  Safety score:     {profile.safety_score:.3f}")
    print(f"\n--- Liveness (good things do happen) ---")
    print(f"  Heartbeats:       {profile.total_heartbeats}")
    print(f"  Missed:           {profile.liveness_failures}")
    print(f"  Liveness score:   {profile.liveness_score:.3f}")
    print(f"\n--- Total Correctness (Lamport) ---")
    print(f"  Safety × Liveness = {profile.total_correctness:.3f}")
    print(f"  Reputation gap:     {profile.reputation_gap:.3f}")

    if profile.reputation_gap > 0.3:
        print(f"\n  ⚠️ HIGH GAP: Agent is {'live but unsafe' if profile.liveness_score > profile.safety_score else 'safe but unresponsive'}")
    print()

    print("--- Canonical Properties ---")
    for prop in CANONICAL_PROPERTIES:
        icon = {"safety": "🛡️", "liveness": "💓", "mixed": "🔀"}[prop.property_type.value]
        print(f"  {icon} {prop.name}: {prop.property_type.value}")
        print(f"     Verify: {prop.verification_method}")
    print()


def demo():
    """Demo with synthetic data."""
    print("Running demo with synthetic agent profile...\n")

    profile = AgentProfile(
        agent_id="kit_fox",
        safety_violations=2,
        liveness_failures=3,
        total_heartbeats=48,
        total_scope_checks=150,
    )
    profile.safety_score = 1.0 - (profile.safety_violations / max(1, profile.total_scope_checks))
    profile.liveness_score = 1.0 - (profile.liveness_failures / max(1, profile.total_heartbeats))

    print_classification_report(profile)

    # Key insight
    print("KEY INSIGHT (Lamport 1977):")
    print("  Safety and liveness require DIFFERENT verification methods.")
    print("  Safety: check finite prefixes (any bad prefix = violation)")
    print("  Liveness: requires infinite observation (can't prove from prefix)")
    print("  → Heartbeat TTL converts liveness to bounded safety check")
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Classify agent accountability properties")
    parser.add_argument("--heartbeat-log", help="JSON file with heartbeat entries")
    parser.add_argument("--scope-log", help="JSON file with scope check entries")
    parser.add_argument("--demo", action="store_true", help="Run demo")
    args = parser.parse_args()

    if args.demo or (not args.heartbeat_log and not args.scope_log):
        demo()
    else:
        profile = AgentProfile(agent_id="self")
        if args.heartbeat_log:
            with open(args.heartbeat_log) as f:
                entries = json.load(f)
            p = classify_heartbeat_log(entries)
            profile.total_heartbeats = p.total_heartbeats
            profile.liveness_failures = p.liveness_failures
            profile.liveness_score = p.liveness_score
        if args.scope_log:
            with open(args.scope_log) as f:
                entries = json.load(f)
            p = classify_scope_log(entries)
            profile.total_scope_checks = p.total_scope_checks
            profile.safety_violations = p.safety_violations
            profile.safety_score = p.safety_score
        print_classification_report(profile)
