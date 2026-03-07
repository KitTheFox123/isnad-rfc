#!/usr/bin/env python3
"""scope-expiry-enforcer.py — Enforce short-lived scope certificates for agent delegation.

Implements the CT-inspired model: scopes expire, no revocation needed.
Each heartbeat = new leaf in the scope log. Expired scope = no authority.

Usage:
    python3 scope-expiry-enforcer.py [--ttl SECONDS] [--heartbeat-interval SECONDS]

Generates scope certificates, tracks expiry, and reports violations
when an agent acts after its scope has lapsed.
"""

import argparse
import hashlib
import json
import time
import random
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class ScopeCert:
    """A short-lived scope certificate."""
    agent_id: str
    principal: str
    scope_hash: str  # SHA-256 of the scope document (e.g., HEARTBEAT.md)
    issued_at: float
    ttl_seconds: float
    cert_id: str = field(default_factory=lambda: hashlib.sha256(
        f"{time.time()}{random.random()}".encode()
    ).hexdigest()[:16])

    @property
    def expires_at(self) -> float:
        return self.issued_at + self.ttl_seconds

    def is_valid(self, at_time: Optional[float] = None) -> bool:
        t = at_time or time.time()
        return t < self.expires_at

    def remaining(self, at_time: Optional[float] = None) -> float:
        t = at_time or time.time()
        return max(0, self.expires_at - t)


@dataclass
class AgentAction:
    """An action taken by an agent."""
    agent_id: str
    action_type: str  # "post", "reply", "build", "email"
    timestamp: float
    cert_id: Optional[str] = None


class ScopeExpiryEnforcer:
    """Tracks scope certificates and flags expired-scope actions."""

    def __init__(self, ttl_seconds: float = 2400, heartbeat_interval: float = 1200):
        self.ttl = ttl_seconds
        self.heartbeat_interval = heartbeat_interval
        self.certs: list[ScopeCert] = []
        self.actions: list[AgentAction] = []
        self.violations: list[dict] = []

    def issue_cert(self, agent_id: str, principal: str, scope_doc: str,
                   at_time: Optional[float] = None) -> ScopeCert:
        scope_hash = hashlib.sha256(scope_doc.encode()).hexdigest()
        cert = ScopeCert(
            agent_id=agent_id,
            principal=principal,
            scope_hash=scope_hash,
            issued_at=at_time or time.time(),
            ttl_seconds=self.ttl,
        )
        self.certs.append(cert)
        return cert

    def latest_cert(self, agent_id: str) -> Optional[ScopeCert]:
        agent_certs = [c for c in self.certs if c.agent_id == agent_id]
        return max(agent_certs, key=lambda c: c.issued_at) if agent_certs else None

    def record_action(self, action: AgentAction) -> dict:
        self.actions.append(action)
        cert = self.latest_cert(action.agent_id)

        result = {
            "action": action.action_type,
            "agent": action.agent_id,
            "timestamp": action.timestamp,
        }

        if cert is None:
            result["status"] = "VIOLATION"
            result["reason"] = "no_cert_issued"
            self.violations.append(result)
        elif not cert.is_valid(action.timestamp):
            result["status"] = "VIOLATION"
            result["reason"] = "cert_expired"
            result["expired_ago_s"] = round(action.timestamp - cert.expires_at, 1)
            result["cert_id"] = cert.cert_id
            self.violations.append(result)
        else:
            result["status"] = "VALID"
            result["remaining_s"] = round(cert.remaining(action.timestamp), 1)
            result["cert_id"] = cert.cert_id

        return result

    def simulate(self, n_heartbeats: int = 10, n_actions_per_beat: int = 5,
                 drift_probability: float = 0.15) -> dict:
        """Simulate agent actions across heartbeats with occasional drift."""
        agent_id = "kit"
        principal = "ilya"
        scope_doc = "HEARTBEAT.md v" + str(int(time.time()))

        sim_time = 0.0  # Use relative time for simulation
        results = []

        for beat in range(n_heartbeats):
            # Issue cert at start of heartbeat (unless drifting)
            if random.random() > drift_probability:
                cert = self.issue_cert(agent_id, principal, scope_doc + str(beat),
                                       at_time=sim_time)
                results.append({
                    "event": "cert_issued",
                    "beat": beat,
                    "cert_id": cert.cert_id,
                    "ttl": self.ttl,
                })
            else:
                results.append({
                    "event": "cert_skipped",
                    "beat": beat,
                    "reason": "simulated_drift",
                })

            # Generate actions throughout the heartbeat interval
            for i in range(n_actions_per_beat):
                action_time = sim_time + random.uniform(0, self.heartbeat_interval)
                # Some actions happen after TTL (late actions)
                if random.random() < 0.1:
                    action_time = sim_time + self.ttl + random.uniform(60, 600)

                action = AgentAction(
                    agent_id=agent_id,
                    action_type=random.choice(["post", "reply", "build", "email"]),
                    timestamp=action_time,
                )
                result = self.record_action(action)
                results.append(result)

            sim_time += self.heartbeat_interval

        # Summary
        total_actions = len(self.actions)
        total_violations = len(self.violations)
        violation_rate = total_violations / total_actions if total_actions else 0

        return {
            "config": {
                "ttl_seconds": self.ttl,
                "heartbeat_interval": self.heartbeat_interval,
                "n_heartbeats": n_heartbeats,
                "drift_probability": drift_probability,
            },
            "summary": {
                "total_actions": total_actions,
                "valid_actions": total_actions - total_violations,
                "violations": total_violations,
                "violation_rate": round(violation_rate, 4),
                "violation_reasons": {
                    "cert_expired": sum(1 for v in self.violations if v["reason"] == "cert_expired"),
                    "no_cert_issued": sum(1 for v in self.violations if v["reason"] == "no_cert_issued"),
                },
                "certs_issued": len(self.certs),
            },
            "verdict": "PASS" if violation_rate < 0.05 else "WARN" if violation_rate < 0.15 else "FAIL",
        }


def main():
    parser = argparse.ArgumentParser(description="Scope expiry enforcer simulation")
    parser.add_argument("--ttl", type=int, default=2400, help="Cert TTL in seconds (default: 2400 = 40min)")
    parser.add_argument("--heartbeat-interval", type=int, default=1200, help="Heartbeat interval in seconds")
    parser.add_argument("--heartbeats", type=int, default=10, help="Number of heartbeats to simulate")
    parser.add_argument("--drift", type=float, default=0.15, help="Probability of skipping cert renewal")
    args = parser.parse_args()

    enforcer = ScopeExpiryEnforcer(ttl_seconds=args.ttl, heartbeat_interval=args.heartbeat_interval)
    result = enforcer.simulate(n_heartbeats=args.heartbeats, drift_probability=args.drift)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
