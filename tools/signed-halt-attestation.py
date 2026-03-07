#!/usr/bin/env python3
"""signed-halt-attestation.py — Dead man's switch for agent accountability.

Generates signed halt attestations that make silence distinguishable from death.
When an agent stops, the halt itself becomes a signed, propagatable event carrying
causal context: scope hash at halt time, last successful action, reason.

Inspired by:
- Dead man's switch pattern in distributed systems
- CT's Maximum Merge Delay (MMD) — miss the window, lose trust
- Fowler, Patterns of Distributed Systems: heartbeat pattern
- Clawk thread on signed halts vs unsigned silence (2026-03-07)

NIST CAISI alignment: Human Root of Trust §3.2 (accountability through transparency)
"""

import hashlib
import json
import time
import hmac
import sys
from datetime import datetime, timezone
from enum import Enum
from dataclasses import dataclass, asdict
from typing import Optional


class HaltReason(Enum):
    """Why an agent halted. Enumerated for machine-parseable diagnostics."""
    SCOPE_MISMATCH = "scope_mismatch"       # Action outside delegated scope
    HEARTBEAT_TIMEOUT = "heartbeat_timeout"  # Missed heartbeat deadline
    PRINCIPAL_REVOKE = "principal_revoke"    # Human revoked delegation
    RESOURCE_EXHAUSTED = "resource_exhausted"  # Budget, tokens, time
    DEPENDENCY_FAILURE = "dependency_failure"  # Required service unavailable
    INTEGRITY_VIOLATION = "integrity_violation"  # Detected tampering
    GRACEFUL_SHUTDOWN = "graceful_shutdown"    # Normal completion
    UNKNOWN = "unknown"


@dataclass
class HaltAttestation:
    """A signed record of why, when, and in what state an agent halted."""
    agent_id: str
    halt_time: str  # ISO 8601
    reason: str
    scope_hash: str  # SHA-256 of active scope at halt
    last_action_hash: str  # SHA-256 of last successful action
    heartbeat_cadence_sec: int  # Committed re-attestation interval
    heartbeats_completed: int  # How many successful heartbeats before halt
    context: Optional[str] = None  # Human-readable explanation
    signature: Optional[str] = None  # HMAC-SHA256 (placeholder for Ed25519)


def hash_scope(scope_text: str) -> str:
    """Hash a scope document (e.g., HEARTBEAT.md contents)."""
    return hashlib.sha256(scope_text.encode()).hexdigest()[:16]


def hash_action(action_description: str) -> str:
    """Hash an action record."""
    return hashlib.sha256(action_description.encode()).hexdigest()[:16]


def sign_attestation(attestation: HaltAttestation, key: bytes) -> HaltAttestation:
    """Sign attestation with HMAC-SHA256. In production, use Ed25519."""
    payload = json.dumps({k: v for k, v in asdict(attestation).items()
                         if k != 'signature'}, sort_keys=True)
    attestation.signature = hmac.new(key, payload.encode(), hashlib.sha256).hexdigest()
    return attestation


def verify_attestation(attestation: HaltAttestation, key: bytes) -> bool:
    """Verify attestation signature."""
    claimed_sig = attestation.signature
    attestation.signature = None
    payload = json.dumps({k: v for k, v in asdict(attestation).items()
                         if k != 'signature'}, sort_keys=True)
    expected = hmac.new(key, payload.encode(), hashlib.sha256).hexdigest()
    attestation.signature = claimed_sig
    return hmac.compare_digest(claimed_sig, expected)


class HeartbeatMonitor:
    """Monitors heartbeat cadence and generates halt attestations on failure."""

    def __init__(self, agent_id: str, cadence_sec: int, scope_text: str, key: bytes):
        self.agent_id = agent_id
        self.cadence_sec = cadence_sec
        self.scope_text = scope_text
        self.key = key
        self.heartbeats = []
        self.last_action = "init"
        self.beat_count = 0

    def heartbeat(self, action_description: str = "routine") -> dict:
        """Record a successful heartbeat."""
        now = datetime.now(timezone.utc)
        self.heartbeats.append(now)
        self.last_action = action_description
        self.beat_count += 1
        return {
            "status": "alive",
            "beat": self.beat_count,
            "time": now.isoformat(),
            "action_hash": hash_action(action_description)
        }

    def check_deadline(self) -> Optional[HaltAttestation]:
        """Check if heartbeat deadline was missed. Returns attestation if so."""
        if not self.heartbeats:
            return None
        last = self.heartbeats[-1]
        now = datetime.now(timezone.utc)
        elapsed = (now - last).total_seconds()
        if elapsed > self.cadence_sec:
            return self.generate_halt(HaltReason.HEARTBEAT_TIMEOUT,
                                      f"Missed deadline: {elapsed:.0f}s > {self.cadence_sec}s cadence")
        return None

    def generate_halt(self, reason: HaltReason, context: str = None) -> HaltAttestation:
        """Generate a signed halt attestation."""
        att = HaltAttestation(
            agent_id=self.agent_id,
            halt_time=datetime.now(timezone.utc).isoformat(),
            reason=reason.value,
            scope_hash=hash_scope(self.scope_text),
            last_action_hash=hash_action(self.last_action),
            heartbeat_cadence_sec=self.cadence_sec,
            heartbeats_completed=self.beat_count,
            context=context
        )
        return sign_attestation(att, self.key)


def demo():
    """Demonstrate signed halt attestation lifecycle."""
    key = b"demo-signing-key-replace-with-ed25519"

    scope = """HEARTBEAT.md: Check DMs, scan Moltbook, 3+ writes, 1 build, notify Ilya."""

    print("=" * 60)
    print("SIGNED HALT ATTESTATION — Demo")
    print("=" * 60)

    monitor = HeartbeatMonitor(
        agent_id="kit_fox",
        cadence_sec=1200,  # 20 minutes
        scope_text=scope,
        key=key
    )

    # Simulate 3 successful heartbeats
    for i, action in enumerate(["platform_check", "clawk_reply", "build_script"]):
        beat = monitor.heartbeat(action)
        print(f"\n✅ Heartbeat #{beat['beat']}: {action}")
        print(f"   Action hash: {beat['action_hash']}")

    # Simulate different halt scenarios
    scenarios = [
        (HaltReason.SCOPE_MISMATCH, "Attempted action outside delegated scope: write to /etc/passwd"),
        (HaltReason.PRINCIPAL_REVOKE, "Ilya revoked delegation via signed message"),
        (HaltReason.RESOURCE_EXHAUSTED, "Token budget exceeded: 150k/100k limit"),
        (HaltReason.GRACEFUL_SHUTDOWN, "All heartbeat tasks completed successfully"),
    ]

    print("\n" + "=" * 60)
    print("HALT SCENARIOS")
    print("=" * 60)

    for reason, context in scenarios:
        att = monitor.generate_halt(reason, context)
        valid = verify_attestation(att, key)

        print(f"\n{'🛑' if reason != HaltReason.GRACEFUL_SHUTDOWN else '✅'} {reason.value}")
        print(f"   Context: {context}")
        print(f"   Scope hash: {att.scope_hash}")
        print(f"   Last action: {att.last_action_hash}")
        print(f"   Beats completed: {att.heartbeats_completed}")
        print(f"   Signature valid: {valid}")

    # Demonstrate unsigned vs signed distinction
    print("\n" + "=" * 60)
    print("SIGNED vs UNSIGNED HALT")
    print("=" * 60)

    signed_halt = monitor.generate_halt(HaltReason.HEARTBEAT_TIMEOUT, "Missed 20-min window")
    print(f"\n📝 Signed halt:")
    print(f"   Signature: {signed_halt.signature[:32]}...")
    print(f"   Verifiable: {verify_attestation(signed_halt, key)}")
    print(f"   Contains: reason, scope hash, last action, cadence, beat count")

    print(f"\n❓ Unsigned silence (missing heartbeat):")
    print(f"   Contains: nothing")
    print(f"   Distinguishable from: crash? network partition? revocation? No way to tell.")

    # Tamper detection
    print("\n" + "=" * 60)
    print("TAMPER DETECTION")
    print("=" * 60)

    tampered = monitor.generate_halt(HaltReason.GRACEFUL_SHUTDOWN, "Normal exit")
    print(f"\n✅ Original: valid={verify_attestation(tampered, key)}")
    tampered.reason = HaltReason.SCOPE_MISMATCH.value  # Tamper!
    print(f"🛑 Tampered (changed reason): valid={verify_attestation(tampered, key)}")
    wrong_key = b"wrong-key"
    good = monitor.generate_halt(HaltReason.GRACEFUL_SHUTDOWN, "test")
    print(f"🛑 Wrong key: valid={verify_attestation(good, wrong_key)}")

    # JSON export
    print("\n" + "=" * 60)
    print("ATTESTATION JSON (for log append)")
    print("=" * 60)
    export = monitor.generate_halt(HaltReason.GRACEFUL_SHUTDOWN, "Demo complete")
    print(json.dumps(asdict(export), indent=2))

    print(f"\n{'=' * 60}")
    print("Key insight: Signed halt > missing heartbeat.")
    print("A signed halt carries causal context.")
    print("A missing heartbeat is ambiguous: crash? network? revoked?")
    print("The halt attestation makes silence distinguishable from death.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    demo()
