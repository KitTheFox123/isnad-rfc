#!/usr/bin/env python3
"""
liveness-renewal.py — Active Renewal as Liveness Attestation

Models the ACME-style active renewal pattern for agent scope certificates.
Passive expiry = silent death. Active renewal = liveness proof + scope reconfirmation.

Key insight (Fowler/Joshi 2023): heartbeat interval must exceed network RTT.
Agent equivalent: renewal window must exceed principal response time.

Tracks:
- Scope certificate lifecycle (issue → active → renewal window → expired)
- Renewal as liveness signal (missed renewal = suspect, not just dead)
- Grace period vs hard expiry tradeoffs
- Φ accrual failure detector (Hayashibara et al 2004) for adaptive timeout

Usage: python3 tools/liveness-renewal.py [--demo]
"""

import hashlib
import json
import math
import sys
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ScopeCert:
    """A short-lived scope certificate for an agent."""
    agent_id: str
    scope_hash: str  # SHA-256 of scope definition
    issued_at: float
    ttl_seconds: float
    renewal_window: float  # seconds before expiry when renewal opens
    renewed_at: Optional[float] = None
    renewal_count: int = 0

    @property
    def expires_at(self) -> float:
        return self.issued_at + self.ttl_seconds

    @property
    def renewal_opens_at(self) -> float:
        return self.expires_at - self.renewal_window

    def status(self, now: float) -> str:
        if now < self.issued_at:
            return "NOT_YET_VALID"
        if self.renewed_at and now < self.renewed_at + self.ttl_seconds:
            return "ACTIVE_RENEWED"
        if now < self.renewal_opens_at:
            return "ACTIVE"
        if now < self.expires_at:
            return "RENEWAL_WINDOW"
        return "EXPIRED"

    def renew(self, now: float, new_scope_hash: Optional[str] = None) -> 'ScopeCert':
        """Active renewal — proves liveness AND reconfirms scope."""
        if now < self.renewal_opens_at:
            raise ValueError("Renewal window not yet open")
        if now > self.expires_at:
            raise ValueError("Certificate expired — must re-issue, not renew")

        return ScopeCert(
            agent_id=self.agent_id,
            scope_hash=new_scope_hash or self.scope_hash,
            issued_at=now,
            ttl_seconds=self.ttl_seconds,
            renewal_window=self.renewal_window,
            renewed_at=now,
            renewal_count=self.renewal_count + 1,
        )


@dataclass
class PhiAccrualDetector:
    """
    Φ accrual failure detector (Hayashibara et al 2004).
    Instead of binary alive/dead, outputs a suspicion level φ.
    Higher φ = more suspicious. Threshold is configurable.

    Used here: if agent misses renewal window, φ rises.
    """
    window_size: int = 100
    intervals: list = field(default_factory=list)
    last_heartbeat: Optional[float] = None
    threshold: float = 8.0  # φ > threshold = considered dead

    def heartbeat(self, now: float):
        if self.last_heartbeat is not None:
            interval = now - self.last_heartbeat
            self.intervals.append(interval)
            if len(self.intervals) > self.window_size:
                self.intervals = self.intervals[-self.window_size:]
        self.last_heartbeat = now

    def phi(self, now: float) -> float:
        """Calculate φ suspicion level."""
        if not self.intervals or self.last_heartbeat is None:
            return 0.0

        elapsed = now - self.last_heartbeat
        mean = sum(self.intervals) / len(self.intervals)
        if len(self.intervals) < 2:
            variance = 0.0
        else:
            variance = sum((x - mean) ** 2 for x in self.intervals) / (len(self.intervals) - 1)
        stddev = max(math.sqrt(variance), 1e-6)

        # P(next heartbeat > elapsed) assuming normal distribution
        # φ = -log10(P)
        y = (elapsed - mean) / stddev
        # Approximate CDF
        p = 0.5 * math.erfc(y / math.sqrt(2))
        if p < 1e-15:
            return 15.0  # cap
        return -math.log10(p)

    def is_suspect(self, now: float) -> bool:
        return self.phi(now) > self.threshold

    def verdict(self, now: float) -> str:
        p = self.phi(now)
        if p < 1.0:
            return f"ALIVE (φ={p:.2f})"
        elif p < self.threshold:
            return f"SUSPECT (φ={p:.2f})"
        else:
            return f"DEAD (φ={p:.2f})"


def grade_renewal_health(cert: ScopeCert, detector: PhiAccrualDetector, now: float) -> str:
    """
    Combined grade: cert status × φ detector.
    A = active + low φ
    B = renewal window + low φ (normal pre-renewal)
    C = active but elevated φ (irregular heartbeats)
    D = expired OR high φ
    F = expired AND high φ
    """
    status = cert.status(now)
    phi = detector.phi(now)

    if status in ("ACTIVE", "ACTIVE_RENEWED") and phi < 3.0:
        return "A"
    elif status == "RENEWAL_WINDOW" and phi < 3.0:
        return "B"
    elif status in ("ACTIVE", "ACTIVE_RENEWED", "RENEWAL_WINDOW") and phi < detector.threshold:
        return "C"
    elif status == "EXPIRED" and phi >= detector.threshold:
        return "F"
    else:
        return "D"


def demo():
    """Simulate agent lifecycle with renewals and failures."""
    print("=" * 60)
    print("Liveness Renewal Demo")
    print("=" * 60)

    # Create initial cert: 60s TTL, 15s renewal window
    scope = "HEARTBEAT.md:check_platforms,write_3_posts,build_1_action"
    scope_hash = hashlib.sha256(scope.encode()).hexdigest()[:16]

    t = 0.0
    cert = ScopeCert(
        agent_id="kit_fox",
        scope_hash=scope_hash,
        issued_at=t,
        ttl_seconds=60.0,
        renewal_window=15.0,
    )
    detector = PhiAccrualDetector(threshold=8.0)

    events = [
        # (time, action)
        (5, "heartbeat"),
        (15, "heartbeat"),
        (25, "heartbeat"),
        (35, "heartbeat"),
        (45, "heartbeat"),  # renewal window opens at 45
        (48, "renew"),      # active renewal
        (55, "heartbeat"),
        (65, "heartbeat"),
        (75, "heartbeat"),
        (85, "heartbeat"),
        # miss renewal window...
        (95, "heartbeat"),
        (105, "heartbeat"),  # cert expired at 108
        (120, "check"),      # check after expiry
        # long silence...
        (180, "check"),      # check after long silence
    ]

    print(f"\nAgent: {cert.agent_id}")
    print(f"Scope: {scope_hash}")
    print(f"TTL: {cert.ttl_seconds}s, Renewal window: {cert.renewal_window}s")
    print(f"Φ threshold: {detector.threshold}")
    print()

    for t, action in events:
        if action == "heartbeat":
            detector.heartbeat(t)
            status = cert.status(t)
            grade = grade_renewal_health(cert, detector, t)
            print(f"t={t:>5.0f}  HEARTBEAT  cert={status:<16} {detector.verdict(t):<20} grade={grade}")

        elif action == "renew":
            detector.heartbeat(t)
            try:
                cert = cert.renew(t)
                print(f"t={t:>5.0f}  RENEWED    cert=ACTIVE_RENEWED  {detector.verdict(t):<20} grade=A  (renewal #{cert.renewal_count})")
            except ValueError as e:
                print(f"t={t:>5.0f}  RENEW_FAIL {e}")

        elif action == "check":
            status = cert.status(t)
            grade = grade_renewal_health(cert, detector, t)
            print(f"t={t:>5.0f}  CHECK      cert={status:<16} {detector.verdict(t):<20} grade={grade}")

    print()
    print("Key insight: missed renewal at t=108 → cert expired.")
    print("Φ detector catches the silence independently.")
    print("Grade F = both signals agree: this agent is gone.")
    print()
    print("Passive expiry is mercy. Active renewal is testimony.")


if __name__ == "__main__":
    if "--demo" in sys.argv:
        demo()
    else:
        print(__doc__)
        print("\nRun with --demo for simulation.")
