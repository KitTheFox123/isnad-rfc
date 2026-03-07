#!/usr/bin/env python3
"""scope-freshness-monitor.py - Monitor agent scope certificate freshness.

Implements the CT-inspired model: short-lived scope commitments with
Maximum Merge Delay (MMD). If no re-sign within TTL, scope is revoked.

Maps to NIST CAISI Theme 4: Accountability & Auditability.
"""

import json
import hashlib
import time
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

def hash_scope(scope_text: str) -> str:
    """SHA-256 of scope commitment text."""
    return hashlib.sha256(scope_text.encode()).hexdigest()

def create_scope_commitment(principal: str, agent: str, scope_file: str, ttl_minutes: int = 40) -> dict:
    """Create a short-lived scope commitment (like a CT precertificate)."""
    scope_text = Path(scope_file).read_text() if Path(scope_file).exists() else scope_file
    now = datetime.now(timezone.utc)
    commitment = {
        "version": 1,
        "principal": principal,
        "agent": agent,
        "scope_hash": hash_scope(scope_text),
        "issued_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=ttl_minutes)).isoformat(),
        "ttl_minutes": ttl_minutes,
        "mmd_minutes": max(ttl_minutes // 4, 5),  # Max Merge Delay = 25% of TTL
    }
    return commitment

def check_freshness(commitment: dict) -> dict:
    """Check if a scope commitment is still fresh."""
    now = datetime.now(timezone.utc)
    expires = datetime.fromisoformat(commitment["expires_at"])
    mmd = timedelta(minutes=commitment.get("mmd_minutes", 10))
    
    time_left = (expires - now).total_seconds()
    in_mmd = time_left < mmd.total_seconds()
    expired = time_left <= 0
    
    status = "EXPIRED" if expired else "MMD_WARNING" if in_mmd else "FRESH"
    
    return {
        "status": status,
        "scope_hash": commitment["scope_hash"],
        "time_remaining_seconds": max(0, time_left),
        "in_mmd_window": in_mmd,
        "recommendation": {
            "FRESH": "No action needed",
            "MMD_WARNING": "Re-sign scope before expiry",
            "EXPIRED": "HALT — scope expired, no authority to act"
        }[status]
    }

def monitor_log(log_file: str) -> dict:
    """Analyze a scope commitment log for freshness gaps."""
    log_path = Path(log_file)
    if not log_path.exists():
        return {"error": f"Log file {log_file} not found"}
    
    entries = []
    for line in log_path.read_text().strip().split('\n'):
        if line.strip():
            entries.append(json.loads(line))
    
    if not entries:
        return {"entries": 0, "gaps": [], "coverage": 0.0}
    
    gaps = []
    for i in range(1, len(entries)):
        prev_expires = datetime.fromisoformat(entries[i-1]["expires_at"])
        curr_issued = datetime.fromisoformat(entries[i]["issued_at"])
        gap = (curr_issued - prev_expires).total_seconds()
        if gap > 0:
            gaps.append({
                "between": [i-1, i],
                "gap_seconds": gap,
                "severity": "CRITICAL" if gap > 300 else "WARNING"
            })
    
    first = datetime.fromisoformat(entries[0]["issued_at"])
    last = datetime.fromisoformat(entries[-1]["expires_at"])
    total_span = (last - first).total_seconds()
    gap_total = sum(g["gap_seconds"] for g in gaps)
    coverage = (total_span - gap_total) / total_span if total_span > 0 else 0.0
    
    return {
        "entries": len(entries),
        "gaps": gaps,
        "coverage_ratio": round(coverage, 4),
        "grade": "A" if coverage >= 0.99 else "B" if coverage >= 0.95 else "C" if coverage >= 0.90 else "F"
    }

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  scope-freshness-monitor.py create <principal> <agent> <scope_file> [ttl_min]")
        print("  scope-freshness-monitor.py check <commitment.json>")
        print("  scope-freshness-monitor.py monitor <log.jsonl>")
        print("  scope-freshness-monitor.py demo")
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    if cmd == "create":
        principal, agent, scope = sys.argv[2], sys.argv[3], sys.argv[4]
        ttl = int(sys.argv[5]) if len(sys.argv) > 5 else 40
        commitment = create_scope_commitment(principal, agent, scope, ttl)
        print(json.dumps(commitment, indent=2))
    
    elif cmd == "check":
        with open(sys.argv[2]) as f:
            commitment = json.load(f)
        result = check_freshness(commitment)
        print(json.dumps(result, indent=2))
    
    elif cmd == "monitor":
        result = monitor_log(sys.argv[2])
        print(json.dumps(result, indent=2))
    
    elif cmd == "demo":
        print("=== Scope Freshness Monitor Demo ===\n")
        # Create commitment
        c = create_scope_commitment("ilya", "kit", "Check platforms, post research, build tools", 40)
        print("Created commitment:")
        print(json.dumps(c, indent=2))
        print()
        # Check freshness
        result = check_freshness(c)
        print("Freshness check:")
        print(json.dumps(result, indent=2))
        print()
        # Simulate log
        log_entries = []
        base = datetime.now(timezone.utc) - timedelta(hours=3)
        for i in range(5):
            issued = base + timedelta(minutes=i*40)
            entry = {
                "scope_hash": hash_scope(f"scope_{i}"),
                "issued_at": issued.isoformat(),
                "expires_at": (issued + timedelta(minutes=40)).isoformat(),
                "mmd_minutes": 10
            }
            log_entries.append(entry)
        
        # Add a gap
        log_entries[2]["issued_at"] = (base + timedelta(minutes=90)).isoformat()
        
        tmp = Path("/tmp/scope_log.jsonl")
        tmp.write_text('\n'.join(json.dumps(e) for e in log_entries))
        
        result = monitor_log(str(tmp))
        print("Log analysis (with injected gap):")
        print(json.dumps(result, indent=2))
