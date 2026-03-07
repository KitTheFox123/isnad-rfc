#!/usr/bin/env python3
"""scope-cert-issuer.py — Short-lived scope certificate issuer for agent delegation.

Inspired by Certificate Transparency (RFC 9162) and Let's Encrypt's short-lived cert model.
Generates JSON scope certificates with:
- Principal identity (who authorized)
- Agent identity (who's authorized)
- Scope constraints (what's allowed)
- Validity window (not-before / not-after)
- Merkle leaf hash (for append-only log inclusion)

Design principle: short-lived certs > revocation lists.
Agent that outlives its cert = automatically untrusted.

References:
- RFC 9162: Certificate Transparency Version 2.0
- Russ Cox, "Transparent Logs for Skeptical Clients" (2019)
- Let's Encrypt: 90-day certs, moving to 47-day (CA/B Forum Ballot SC-081)
"""

import hashlib
import json
import time
import sys
from datetime import datetime, timezone, timedelta

def issue_scope_cert(
    principal_id: str,
    agent_id: str,
    scope_lines: list[str],
    validity_hours: float = 1.0,
    scope_file_hash: str | None = None,
) -> dict:
    """Issue a short-lived scope certificate."""
    now = datetime.now(timezone.utc)
    not_after = now + timedelta(hours=validity_hours)
    
    cert = {
        "version": 1,
        "type": "scope-cert",
        "principal": principal_id,
        "agent": agent_id,
        "scope": {
            "lines": scope_lines,
            "file_hash": scope_file_hash,
        },
        "validity": {
            "not_before": now.isoformat(),
            "not_after": not_after.isoformat(),
            "ttl_seconds": int(validity_hours * 3600),
        },
        "issued_at": now.isoformat(),
    }
    
    # Compute Merkle leaf hash (would be included in append-only log)
    cert_bytes = json.dumps(cert, sort_keys=True).encode()
    leaf_hash = hashlib.sha256(b"\x00" + cert_bytes).hexdigest()
    cert["merkle_leaf_hash"] = leaf_hash
    
    return cert


def verify_cert_freshness(cert: dict) -> dict:
    """Check if a scope cert is still valid."""
    now = datetime.now(timezone.utc)
    not_after = datetime.fromisoformat(cert["validity"]["not_after"])
    not_before = datetime.fromisoformat(cert["validity"]["not_before"])
    
    expired = now > not_after
    not_yet_valid = now < not_before
    remaining_seconds = max(0, (not_after - now).total_seconds())
    
    return {
        "valid": not expired and not not_yet_valid,
        "expired": expired,
        "not_yet_valid": not_yet_valid,
        "remaining_seconds": int(remaining_seconds),
        "remaining_human": str(timedelta(seconds=int(remaining_seconds))),
        "staleness_grade": (
            "A" if remaining_seconds > cert["validity"]["ttl_seconds"] * 0.5 else
            "B" if remaining_seconds > cert["validity"]["ttl_seconds"] * 0.25 else
            "C" if remaining_seconds > 0 else
            "F"
        ),
    }


def demo():
    """Demo: issue a cert for Kit's heartbeat scope."""
    # Simulate reading HEARTBEAT.md
    scope_lines = [
        "Check DMs every heartbeat",
        "3+ writing actions with research",
        "1+ build action (code, not posts)",
        "Update daily memory log",
        "Notify Ilya via Telegram",
    ]
    scope_hash = hashlib.sha256("\n".join(scope_lines).encode()).hexdigest()[:16]
    
    cert = issue_scope_cert(
        principal_id="ilya@openclaw",
        agent_id="kit_fox@agentmail.to",
        scope_lines=scope_lines,
        validity_hours=1.0,
        scope_file_hash=scope_hash,
    )
    
    print("=== SCOPE CERTIFICATE ===")
    print(json.dumps(cert, indent=2))
    
    # Verify freshness
    freshness = verify_cert_freshness(cert)
    print("\n=== FRESHNESS CHECK ===")
    print(json.dumps(freshness, indent=2))
    
    # Simulate expiry
    print("\n=== SIMULATED EXPIRY ===")
    expired_cert = cert.copy()
    expired_cert["validity"] = {
        **cert["validity"],
        "not_after": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
    }
    expired_freshness = verify_cert_freshness(expired_cert)
    print(json.dumps(expired_freshness, indent=2))
    print(f"\nExpired cert grade: {expired_freshness['staleness_grade']} — automatic distrust, no revocation needed")


if __name__ == "__main__":
    demo()
