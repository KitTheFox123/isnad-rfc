#!/usr/bin/env python3
"""scope-expiry-monitor.py — Detect prospective memory commission errors in agent scope.

Agents, like humans, suffer from "commission errors": continuing to execute
intentions that are no longer active. A scope that expired 3 heartbeats ago
but whose cues still appear in context will trigger stale behavior.

Based on: Möschl et al 2020 (systematic review of PM aftereffects),
Nature HSS Communications 2024 (implementation intentions reduce commission errors).

The fix: explicit scope expiry with "if-then" implementation intentions.
"If scope X has expired, then IGNORE cue Y" — not just "scope X is done."
"""

import json
import hashlib
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


class ScopeStatus(Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    SUPERSEDED = "superseded"  # overwritten by new scope


@dataclass
class ScopeEntry:
    scope_id: str
    description: str
    cues: list[str]  # trigger patterns
    status: ScopeStatus = ScopeStatus.ACTIVE
    created_beat: int = 0
    expiry_beat: Optional[int] = None
    superseded_by: Optional[str] = None
    implementation_intention: Optional[str] = None  # "if X then ignore Y"

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(
            f"{self.scope_id}:{self.description}:{','.join(self.cues)}".encode()
        ).hexdigest()[:16]


@dataclass
class CommissionError:
    """A detected commission error: acting on expired scope."""
    scope_id: str
    cue_matched: str
    current_beat: int
    expired_at_beat: int
    beats_stale: int
    severity: str  # low/medium/high/critical


class ScopeExpiryMonitor:
    def __init__(self):
        self.scopes: dict[str, ScopeEntry] = {}
        self.errors: list[CommissionError] = []
        self.current_beat: int = 0

    def register_scope(self, scope_id: str, description: str, cues: list[str],
                        ttl_beats: int = 1) -> ScopeEntry:
        entry = ScopeEntry(
            scope_id=scope_id,
            description=description,
            cues=cues,
            created_beat=self.current_beat,
            expiry_beat=self.current_beat + ttl_beats,
        )
        # Generate implementation intention for expiry
        cue_str = ", ".join(f'"{c}"' for c in cues)
        entry.implementation_intention = (
            f"IF beat > {entry.expiry_beat} AND cue matches [{cue_str}], "
            f"THEN ignore — scope '{scope_id}' expired."
        )

        # Check if this supersedes an existing scope
        for existing in self.scopes.values():
            if existing.status == ScopeStatus.ACTIVE and existing.scope_id != scope_id:
                overlap = set(existing.cues) & set(cues)
                if overlap:
                    existing.status = ScopeStatus.SUPERSEDED
                    existing.superseded_by = scope_id

        self.scopes[scope_id] = entry
        return entry

    def advance_beat(self):
        self.current_beat += 1
        for scope in self.scopes.values():
            if (scope.status == ScopeStatus.ACTIVE and
                scope.expiry_beat is not None and
                self.current_beat > scope.expiry_beat):
                scope.status = ScopeStatus.EXPIRED

    def check_action(self, action_cue: str) -> Optional[CommissionError]:
        """Check if an action cue matches an expired scope (commission error)."""
        for scope in self.scopes.values():
            if scope.status in (ScopeStatus.EXPIRED, ScopeStatus.SUPERSEDED):
                if action_cue in scope.cues:
                    staleness = self.current_beat - (scope.expiry_beat or scope.created_beat)
                    severity = (
                        "critical" if staleness > 5 else
                        "high" if staleness > 3 else
                        "medium" if staleness > 1 else
                        "low"
                    )
                    error = CommissionError(
                        scope_id=scope.scope_id,
                        cue_matched=action_cue,
                        current_beat=self.current_beat,
                        expired_at_beat=scope.expiry_beat or 0,
                        beats_stale=staleness,
                        severity=severity,
                    )
                    self.errors.append(error)
                    return error
        return None

    def active_intentions(self) -> list[str]:
        """Return all active implementation intentions (for context injection)."""
        return [
            s.implementation_intention
            for s in self.scopes.values()
            if s.status == ScopeStatus.EXPIRED and s.implementation_intention
        ]

    def report(self) -> dict:
        active = [s for s in self.scopes.values() if s.status == ScopeStatus.ACTIVE]
        expired = [s for s in self.scopes.values() if s.status != ScopeStatus.ACTIVE]
        return {
            "current_beat": self.current_beat,
            "active_scopes": len(active),
            "expired_scopes": len(expired),
            "commission_errors": len(self.errors),
            "error_rate": len(self.errors) / max(self.current_beat, 1),
            "active_suppression_rules": self.active_intentions(),
        }


def demo():
    monitor = ScopeExpiryMonitor()

    # Beat 0: Register initial scopes
    monitor.register_scope("deploy-hotfix", "Deploy hotfix to prod", ["deploy", "push", "release"], ttl_beats=2)
    monitor.register_scope("audit-logs", "Check audit logs for anomalies", ["audit", "logs", "check"], ttl_beats=3)

    print("=== Scope Expiry Monitor Demo ===")
    print(f"Registered 2 scopes at beat 0\n")

    # Simulate 6 heartbeats
    actions_per_beat = {
        1: ["deploy", "audit"],      # Both valid
        2: ["deploy", "logs"],        # deploy still valid, logs valid
        3: ["deploy", "check"],       # deploy EXPIRED (commission error!), check valid
        4: ["push", "audit"],         # push EXPIRED, audit EXPIRED
        5: ["release", "logs"],       # Both expired
    }

    for beat in range(1, 6):
        monitor.advance_beat()
        print(f"--- Beat {beat} ---")
        for action in actions_per_beat.get(beat, []):
            error = monitor.check_action(action)
            if error:
                print(f"  ⚠️  COMMISSION ERROR: '{action}' matches expired scope "
                      f"'{error.scope_id}' (stale {error.beats_stale} beats, {error.severity})")
            else:
                print(f"  ✓ '{action}' — valid or no matching scope")

    print(f"\n=== Report ===")
    report = monitor.report()
    print(json.dumps(report, indent=2))

    if report["active_suppression_rules"]:
        print(f"\n=== Active Suppression Rules (inject into context) ===")
        for rule in report["active_suppression_rules"]:
            print(f"  → {rule}")


if __name__ == "__main__":
    demo()
