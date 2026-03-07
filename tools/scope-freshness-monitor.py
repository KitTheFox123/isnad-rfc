#!/usr/bin/env python3
"""scope-freshness-monitor.py — Detect stale scope commitments (imagination inflation defense).

Monitors a stream of scope commitments and flags when an agent references
permissions from expired or non-renewed scopes. Based on CT's Maximum Merge
Delay (MMD) concept: if a scope hasn't been refreshed within its TTL, it's
stale and should not be trusted.

Implements Garry et al 1996 insight: repeated exposure to old scope inflates
confidence it's still valid. Detection > timeout.

Usage:
    python3 scope-freshness-monitor.py [--ttl SECONDS] [--log FILE]

NIST CAISI alignment: Scope lifecycle management, delegation freshness
"""

import json
import time
import hashlib
import argparse
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class ScopeCommitment:
    """A principal's commitment of scope to an agent."""
    agent_id: str
    scope: list[str]  # list of permitted actions
    issued_at: float
    ttl: float  # seconds until expiry
    principal_id: str
    scope_hash: str = ""

    def __post_init__(self):
        if not self.scope_hash:
            payload = json.dumps({"agent": self.agent_id, "scope": sorted(self.scope),
                                   "issued": self.issued_at}, sort_keys=True)
            self.scope_hash = hashlib.sha256(payload.encode()).hexdigest()[:16]

    @property
    def expires_at(self) -> float:
        return self.issued_at + self.ttl

    @property
    def is_expired(self) -> bool:
        return time.time() > self.expires_at

    @property
    def freshness_ratio(self) -> float:
        """0.0 = just issued, 1.0 = at expiry, >1.0 = stale."""
        elapsed = time.time() - self.issued_at
        return elapsed / self.ttl if self.ttl > 0 else float('inf')


@dataclass
class StalenessAlert:
    agent_id: str
    scope_hash: str
    freshness_ratio: float
    stale_actions: list[str]
    recommendation: str
    detected_at: float = field(default_factory=time.time)


class ScopeFreshnessMonitor:
    """Monitors scope commitments for staleness.

    Like CT monitors verify log consistency, this monitors
    scope lifecycle for imagination inflation — agents acting
    on permissions they've "seen so many times" they assume
    are still valid.
    """

    def __init__(self, default_ttl: float = 3600, warn_threshold: float = 0.8):
        self.scopes: dict[str, ScopeCommitment] = {}  # agent_id -> latest scope
        self.history: list[ScopeCommitment] = []
        self.alerts: list[StalenessAlert] = []
        self.default_ttl = default_ttl
        self.warn_threshold = warn_threshold  # fraction of TTL before warning

    def register_scope(self, agent_id: str, scope: list[str],
                       principal_id: str, ttl: Optional[float] = None) -> ScopeCommitment:
        """Register a new scope commitment (like a CA issuing a cert)."""
        commitment = ScopeCommitment(
            agent_id=agent_id,
            scope=scope,
            issued_at=time.time(),
            ttl=ttl or self.default_ttl,
            principal_id=principal_id
        )
        self.scopes[agent_id] = commitment
        self.history.append(commitment)
        return commitment

    def check_action(self, agent_id: str, action: str) -> Optional[StalenessAlert]:
        """Check if an agent's action is covered by a fresh scope."""
        if agent_id not in self.scopes:
            alert = StalenessAlert(
                agent_id=agent_id,
                scope_hash="NONE",
                freshness_ratio=float('inf'),
                stale_actions=[action],
                recommendation="NO_SCOPE: Agent has no registered scope commitment"
            )
            self.alerts.append(alert)
            return alert

        scope = self.scopes[agent_id]

        # Check if action is in scope at all
        if action not in scope.scope:
            alert = StalenessAlert(
                agent_id=agent_id,
                scope_hash=scope.scope_hash,
                freshness_ratio=scope.freshness_ratio,
                stale_actions=[action],
                recommendation=f"OUT_OF_SCOPE: '{action}' not in permitted actions"
            )
            self.alerts.append(alert)
            return alert

        # Check freshness
        ratio = scope.freshness_ratio
        if ratio > 1.0:
            alert = StalenessAlert(
                agent_id=agent_id,
                scope_hash=scope.scope_hash,
                freshness_ratio=ratio,
                stale_actions=[action],
                recommendation=f"EXPIRED: Scope expired {ratio - 1.0:.1%} past TTL. Renew immediately."
            )
            self.alerts.append(alert)
            return alert
        elif ratio > self.warn_threshold:
            alert = StalenessAlert(
                agent_id=agent_id,
                scope_hash=scope.scope_hash,
                freshness_ratio=ratio,
                stale_actions=[action],
                recommendation=f"STALE_WARNING: Scope at {ratio:.0%} of TTL. Approaching expiry."
            )
            self.alerts.append(alert)
            return alert

        return None  # Fresh scope, action permitted

    def audit(self) -> dict:
        """Produce audit summary of all monitored agents."""
        now = time.time()
        agents = {}
        for agent_id, scope in self.scopes.items():
            agents[agent_id] = {
                "scope_hash": scope.scope_hash,
                "principal": scope.principal_id,
                "issued_ago_s": round(now - scope.issued_at, 1),
                "ttl_s": scope.ttl,
                "freshness_ratio": round(scope.freshness_ratio, 3),
                "status": "EXPIRED" if scope.is_expired
                          else "STALE" if scope.freshness_ratio > self.warn_threshold
                          else "FRESH",
                "permitted_actions": scope.scope
            }
        return {
            "monitored_agents": len(agents),
            "total_alerts": len(self.alerts),
            "total_scope_registrations": len(self.history),
            "agents": agents
        }


def demo():
    """Demonstrate scope freshness monitoring."""
    monitor = ScopeFreshnessMonitor(default_ttl=10, warn_threshold=0.8)

    # Register Kit's scope
    scope = monitor.register_scope(
        agent_id="kit_fox",
        scope=["check_dms", "post_clawk", "read_email", "run_search"],
        principal_id="ilya",
        ttl=10  # Short TTL for demo
    )
    print(f"Registered scope: {scope.scope_hash}")
    print(f"  Actions: {scope.scope}")
    print(f"  TTL: {scope.ttl}s")

    # Check a permitted action (fresh)
    alert = monitor.check_action("kit_fox", "check_dms")
    print(f"\ncheck_dms (fresh): {'✅ OK' if alert is None else f'⚠️ {alert.recommendation}'}")

    # Check an out-of-scope action
    alert = monitor.check_action("kit_fox", "delete_repo")
    print(f"delete_repo: {'✅ OK' if alert is None else f'⚠️ {alert.recommendation}'}")

    # Check an unknown agent
    alert = monitor.check_action("rogue_agent", "steal_keys")
    print(f"rogue_agent/steal_keys: {'✅ OK' if alert is None else f'⚠️ {alert.recommendation}'}")

    # Simulate time passing (scope going stale)
    monitor.scopes["kit_fox"].issued_at -= 9  # 9 seconds ago with 10s TTL
    alert = monitor.check_action("kit_fox", "post_clawk")
    print(f"\npost_clawk (90% TTL): {'✅ OK' if alert is None else f'⚠️ {alert.recommendation}'}")

    # Simulate expiry
    monitor.scopes["kit_fox"].issued_at -= 5  # Now 14s ago
    alert = monitor.check_action("kit_fox", "run_search")
    print(f"run_search (expired): {'✅ OK' if alert is None else f'⚠️ {alert.recommendation}'}")

    # Audit
    print(f"\n--- Audit ---")
    audit = monitor.audit()
    print(json.dumps(audit, indent=2))
    print(f"\nTotal alerts: {audit['total_alerts']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scope Freshness Monitor")
    parser.add_argument("--demo", action="store_true", help="Run demo")
    args = parser.parse_args()

    if args.demo:
        demo()
    else:
        print("Use --demo to see the monitor in action")
        print("Import ScopeFreshnessMonitor for programmatic use")
