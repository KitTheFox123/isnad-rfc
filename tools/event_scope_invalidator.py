#!/usr/bin/env python3
"""event_scope_invalidator.py — Event-driven scope invalidation for agent delegation.

Instead of relying on TTL-based scope expiry (timers that say nothing about
whether meaning changed), this tool implements signal-based invalidation:
scopes remain valid until a registered event fires.

Inspired by:
- Oso's context-aware permissions (2025): mid-session risk re-evaluation
- ISACA event-driven access revalidation (Balakrishnan & Francis 2025)
- CT log MMD windows (RFC 9162)
- Dudek & Polczyk (2024) imagination inflation: memory distrust as
  internal invalidation signal

Events can be:
- Context shifts (world state hash changed)
- Behavioral anomalies (KL divergence > threshold)
- External signals (operator revocation, peer attestation failure)
- Temporal (TTL as fallback, not primary mechanism)

Usage:
    python event_scope_invalidator.py demo
    python event_scope_invalidator.py check --scope-file scope.json --events events.json
"""

import hashlib
import json
import sys
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


class EventType(str, Enum):
    CONTEXT_SHIFT = "context_shift"
    BEHAVIORAL_ANOMALY = "behavioral_anomaly"
    OPERATOR_REVOCATION = "operator_revocation"
    PEER_ATTESTATION_FAILURE = "peer_attestation_failure"
    TTL_EXPIRY = "ttl_expiry"
    SCOPE_DRIFT = "scope_drift"


@dataclass
class InvalidationEvent:
    event_type: EventType
    timestamp: float
    details: str
    severity: float  # 0.0 - 1.0

    def to_dict(self):
        d = asdict(self)
        d["event_type"] = self.event_type.value
        return d


@dataclass
class ScopeRecord:
    scope_hash: str
    world_state_hash: str
    issued_at: float
    ttl_seconds: float  # fallback TTL
    invalidation_events: list = field(default_factory=list)
    valid: bool = True

    def check_ttl(self) -> Optional[InvalidationEvent]:
        if time.time() - self.issued_at > self.ttl_seconds:
            return InvalidationEvent(
                event_type=EventType.TTL_EXPIRY,
                timestamp=time.time(),
                details=f"TTL expired: {self.ttl_seconds}s since issuance",
                severity=0.5,
            )
        return None

    def check_context(self, current_world_hash: str) -> Optional[InvalidationEvent]:
        if current_world_hash != self.world_state_hash:
            return InvalidationEvent(
                event_type=EventType.CONTEXT_SHIFT,
                timestamp=time.time(),
                details=f"World state changed: {self.world_state_hash[:12]}→{current_world_hash[:12]}",
                severity=0.8,
            )
        return None

    def check_behavioral(self, kl_divergence: float, threshold: float = 0.3) -> Optional[InvalidationEvent]:
        if kl_divergence > threshold:
            return InvalidationEvent(
                event_type=EventType.BEHAVIORAL_ANOMALY,
                timestamp=time.time(),
                details=f"KL divergence {kl_divergence:.3f} > threshold {threshold}",
                severity=min(1.0, kl_divergence),
            )
        return None

    def invalidate(self, event: InvalidationEvent):
        self.invalidation_events.append(event.to_dict())
        self.valid = False

    def evaluate_all(self, current_world_hash: str = None, kl_divergence: float = 0.0) -> list:
        """Run all checks, return list of fired events."""
        fired = []

        ttl_event = self.check_ttl()
        if ttl_event:
            fired.append(ttl_event)

        if current_world_hash:
            ctx_event = self.check_context(current_world_hash)
            if ctx_event:
                fired.append(ctx_event)

        beh_event = self.check_behavioral(kl_divergence)
        if beh_event:
            fired.append(beh_event)

        for event in fired:
            self.invalidate(event)

        return fired


def hash_state(state_dict: dict) -> str:
    return hashlib.sha256(json.dumps(state_dict, sort_keys=True).encode()).hexdigest()


def demo():
    print("=== Event-Driven Scope Invalidation Demo ===\n")

    # Create scope with known world state
    world_v1 = {"heartbeat_file": "HEARTBEAT.md", "version": 42, "operator": "ilya"}
    scope = ScopeRecord(
        scope_hash=hash_state({"action": "monitor_network", "constraints": ["read_only"]}),
        world_state_hash=hash_state(world_v1),
        issued_at=time.time() - 100,  # issued 100s ago
        ttl_seconds=300,  # 5 min TTL fallback
    )
    print(f"Scope valid: {scope.valid}")
    print(f"World state: {scope.world_state_hash[:16]}...")

    # Check 1: no changes
    fired = scope.evaluate_all(current_world_hash=hash_state(world_v1), kl_divergence=0.1)
    print(f"\nCheck 1 (no changes): {len(fired)} events fired → valid={scope.valid}")

    # Reset for next demo
    scope.valid = True
    scope.invalidation_events = []

    # Check 2: context shift (breach detected!)
    world_v2 = {"heartbeat_file": "HEARTBEAT.md", "version": 42, "operator": "ilya", "breach_detected": True}
    fired = scope.evaluate_all(current_world_hash=hash_state(world_v2), kl_divergence=0.1)
    print(f"\nCheck 2 (breach!): {len(fired)} events fired → valid={scope.valid}")
    for e in fired:
        print(f"  ⚡ {e.event_type.value}: {e.details} (severity={e.severity})")

    # Reset for next demo
    scope.valid = True
    scope.invalidation_events = []

    # Check 3: behavioral anomaly
    fired = scope.evaluate_all(current_world_hash=hash_state(world_v1), kl_divergence=0.85)
    print(f"\nCheck 3 (behavioral anomaly): {len(fired)} events fired → valid={scope.valid}")
    for e in fired:
        print(f"  ⚡ {e.event_type.value}: {e.details} (severity={e.severity})")

    # Key insight
    print("\n--- Key Insight ---")
    print('"monitor the network" before a breach ≠ after.')
    print("Same scope text, different world state → invalidation event fires.")
    print("Expiry is the fallback. Detection > timer.")
    print(f"\nReferences:")
    print("  - Oso context-aware permissions (Mestci 2025)")
    print("  - ISACA event-driven revalidation (Balakrishnan & Francis 2025)")
    print("  - Dudek & Polczyk (2024) — imagination inflation: imagining")
    print("    an event inflates confidence it occurred. Agent scope analog:")
    print("    repeated use of stale scope inflates confidence it's still valid.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "demo":
        demo()
    else:
        print("Usage: python event_scope_invalidator.py demo")
        print("  Event-driven scope invalidation for agent delegation.")
        print("  Scopes remain valid until a signal fires, not until a timer expires.")
