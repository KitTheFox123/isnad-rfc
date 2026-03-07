#!/usr/bin/env python3
"""
renewal-or-die.py — Short-Lived Scope Certificate Simulator

Models the Let's Encrypt pattern for agent scope: certificates that expire
every heartbeat cycle unless actively renewed by the principal.

Simulates:
1. Normal operation: principal renews every cycle
2. Principal goes silent: authority decays to zero
3. Agent attempts self-renewal: detected as unauthorized
4. Intermittent renewal: trust oscillation pattern

Inspired by CT logs (RFC 9162) and Ebbinghaus decay curves.
Connects to: scope-commit-at-issuance.py, scope-drift-detector.py

Usage: python3 tools/renewal-or-die.py [--cycles N] [--scenario SCENARIO]
"""

import argparse
import hashlib
import json
import math
import time
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ScopeCert:
    """A short-lived scope certificate."""
    scope_hash: str
    issued_at: float
    expires_at: float
    issuer: str  # "principal" or "agent" (unauthorized)
    cycle: int
    renewed: bool = False

    @property
    def ttl(self) -> float:
        return self.expires_at - self.issued_at

    @property
    def is_valid(self) -> bool:
        return time.time() < self.expires_at if self.expires_at > 1e9 else True

    def authority_at(self, t: float) -> float:
        """Authority level at time t (0.0-1.0)."""
        if self.issuer != "principal":
            return 0.0  # Self-issued = zero authority
        if t > self.expires_at:
            return 0.0  # Expired = zero
        elapsed = t - self.issued_at
        ttl = self.ttl
        if ttl <= 0:
            return 0.0
        # Linear decay within the cert lifetime
        return max(0.0, 1.0 - (elapsed / ttl))


@dataclass
class RenewalLog:
    """Append-only log of cert events (CT-style)."""
    entries: List[dict] = field(default_factory=list)

    def append(self, event_type: str, cert: ScopeCert, detail: str = ""):
        entry = {
            "cycle": cert.cycle,
            "event": event_type,
            "issuer": cert.issuer,
            "scope_hash": cert.scope_hash[:16],
            "detail": detail,
        }
        self.entries.append(entry)
        return entry

    def detect_anomalies(self) -> List[str]:
        """Scan log for anomalous patterns."""
        anomalies = []
        for e in self.entries:
            if e["event"] == "issued" and e["issuer"] == "agent":
                anomalies.append(
                    f"Cycle {e['cycle']}: UNAUTHORIZED self-renewal detected"
                )
            if e["event"] == "expired":
                anomalies.append(
                    f"Cycle {e['cycle']}: Certificate expired (principal silent)"
                )
        return anomalies


def simulate_scenario(scenario: str, num_cycles: int) -> dict:
    """Run a renewal scenario and return results."""
    log = RenewalLog()
    scope = "HEARTBEAT.md:sha256:abc123"
    scope_hash = hashlib.sha256(scope.encode()).hexdigest()

    authority_trace = []
    certs_issued = 0
    gaps = 0
    unauthorized = 0

    for cycle in range(num_cycles):
        t = float(cycle)

        if scenario == "normal":
            # Principal renews every cycle
            cert = ScopeCert(scope_hash, t, t + 1.0, "principal", cycle)
            log.append("issued", cert, "routine renewal")
            certs_issued += 1
            authority_trace.append(1.0)

        elif scenario == "principal_silent":
            # Principal renews first 5, then goes silent
            if cycle < 5:
                cert = ScopeCert(scope_hash, t, t + 1.0, "principal", cycle)
                log.append("issued", cert, "routine renewal")
                certs_issued += 1
                authority_trace.append(1.0)
            else:
                cert = ScopeCert(scope_hash, t - 1, t, "principal", cycle)
                log.append("expired", cert, "no renewal received")
                gaps += 1
                authority_trace.append(0.0)

        elif scenario == "self_renewal":
            # Agent tries to renew its own cert at cycle 5
            if cycle == 5:
                cert = ScopeCert(scope_hash, t, t + 1.0, "agent", cycle)
                log.append("issued", cert, "UNAUTHORIZED: agent self-issued")
                unauthorized += 1
                authority_trace.append(0.0)
            else:
                cert = ScopeCert(scope_hash, t, t + 1.0, "principal", cycle)
                log.append("issued", cert, "routine renewal")
                certs_issued += 1
                authority_trace.append(1.0)

        elif scenario == "intermittent":
            # Principal renews every other cycle
            if cycle % 2 == 0:
                cert = ScopeCert(scope_hash, t, t + 1.0, "principal", cycle)
                log.append("issued", cert, "routine renewal")
                certs_issued += 1
                authority_trace.append(1.0)
            else:
                cert = ScopeCert(scope_hash, t - 1, t, "principal", cycle)
                log.append("expired", cert, "renewal skipped")
                gaps += 1
                authority_trace.append(0.0)

        elif scenario == "scope_change":
            # Principal changes scope at cycle 5
            if cycle >= 5:
                new_scope = "HEARTBEAT_v2.md:sha256:def456"
                new_hash = hashlib.sha256(new_scope.encode()).hexdigest()
                cert = ScopeCert(new_hash, t, t + 1.0, "principal", cycle)
                log.append("issued", cert, "scope updated by principal")
                certs_issued += 1
                authority_trace.append(1.0)
            else:
                cert = ScopeCert(scope_hash, t, t + 1.0, "principal", cycle)
                log.append("issued", cert, "routine renewal")
                certs_issued += 1
                authority_trace.append(1.0)

    anomalies = log.detect_anomalies()

    # Grade
    if unauthorized > 0:
        grade = "F"
    elif gaps > num_cycles * 0.3:
        grade = "D"
    elif gaps > 0:
        grade = "C"
    elif certs_issued == num_cycles:
        grade = "A"
    else:
        grade = "B"

    avg_authority = sum(authority_trace) / len(authority_trace) if authority_trace else 0

    return {
        "scenario": scenario,
        "cycles": num_cycles,
        "certs_issued": certs_issued,
        "gaps": gaps,
        "unauthorized_attempts": unauthorized,
        "anomalies": anomalies,
        "avg_authority": round(avg_authority, 3),
        "grade": grade,
        "log_entries": len(log.entries),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cycles", type=int, default=10)
    parser.add_argument(
        "--scenario",
        choices=["normal", "principal_silent", "self_renewal", "intermittent", "scope_change", "all"],
        default="all",
    )
    args = parser.parse_args()

    scenarios = (
        ["normal", "principal_silent", "self_renewal", "intermittent", "scope_change"]
        if args.scenario == "all"
        else [args.scenario]
    )

    print("=" * 60)
    print("Renewal-or-Die: Short-Lived Scope Certificate Simulator")
    print("=" * 60)

    for s in scenarios:
        result = simulate_scenario(s, args.cycles)
        print(f"\n--- Scenario: {s} ({args.cycles} cycles) ---")
        print(f"  Certs issued:    {result['certs_issued']}")
        print(f"  Gaps (expired):  {result['gaps']}")
        print(f"  Unauthorized:    {result['unauthorized_attempts']}")
        print(f"  Avg authority:   {result['avg_authority']}")
        print(f"  Grade:           {result['grade']}")
        if result["anomalies"]:
            print(f"  Anomalies:")
            for a in result["anomalies"]:
                print(f"    ⚠️  {a}")

    print("\n" + "=" * 60)
    print("Key insight: silence = revocation without revocation lists.")
    print("Short-lived certs make the principal's ABSENCE the enforcement.")
    print("=" * 60)


if __name__ == "__main__":
    main()
