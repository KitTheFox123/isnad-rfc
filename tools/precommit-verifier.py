#!/usr/bin/env python3
"""precommit-verifier.py — Verify pre-commitment hashes against actual outputs.

Implements the Ulysses pattern: hash intent before action, compare after.
Based on Elster (1979) "Ulysses and the Sirens" and CT log MMD model.

The commit window (time between hash publication and action) IS the security
parameter. Shorter window = harder to forge = higher latency cost.

Usage:
    # Create a pre-commitment
    python precommit-verifier.py commit --intent "deploy version 2.1" --channel stdout

    # Verify after action
    python precommit-verifier.py verify --hash <hash> --actual "deploy version 2.1" --committed-at <ISO8601>

    # Analyze commit window security
    python precommit-verifier.py analyze-window --window-seconds 60
"""

import argparse
import hashlib
import json
import math
import sys
from datetime import datetime, timezone


def commit_hash(intent: str, nonce: str = "") -> dict:
    """Create a pre-commitment hash of an intended action."""
    payload = f"{intent}|{nonce}" if nonce else intent
    h = hashlib.sha256(payload.encode()).hexdigest()
    now = datetime.now(timezone.utc)
    return {
        "hash": h,
        "algorithm": "sha256",
        "committed_at": now.isoformat(),
        "nonce_used": bool(nonce),
        "payload_length": len(intent),
    }


def verify(committed_hash: str, actual: str, nonce: str = "",
           committed_at: str | None = None, max_window_seconds: float = 86400) -> dict:
    """Verify a pre-commitment against actual output."""
    payload = f"{actual}|{nonce}" if nonce else actual
    actual_hash = hashlib.sha256(payload.encode()).hexdigest()
    match = committed_hash == actual_hash

    result = {
        "match": match,
        "committed_hash": committed_hash,
        "actual_hash": actual_hash,
    }

    if committed_at:
        try:
            ct = datetime.fromisoformat(committed_at)
            now = datetime.now(timezone.utc)
            window = (now - ct).total_seconds()
            result["window_seconds"] = round(window, 1)
            result["window_valid"] = window <= max_window_seconds
            result["max_window_seconds"] = max_window_seconds
        except ValueError:
            result["window_error"] = "Could not parse committed_at timestamp"

    return result


def analyze_window(window_seconds: float) -> dict:
    """Analyze the security properties of a commit window.

    Model: forgery requires compromising BOTH the commit channel and the
    action channel within the window. Probability of simultaneous compromise
    decreases with shorter windows (assuming independent channels).

    P(forgery) = P(compromise_commit) * P(compromise_action) * P(within_window)
    P(within_window) ≈ window / reference_period

    Reference: CT Maximum Merge Delay = 86400s (24h).
    """
    reference_period = 86400.0  # 24h in seconds (CT MMD)
    p_within = min(window_seconds / reference_period, 1.0)

    # Assume independent channel compromise probabilities
    scenarios = {
        "strong_channels": {"p_commit": 0.001, "p_action": 0.001},
        "moderate_channels": {"p_commit": 0.01, "p_action": 0.01},
        "weak_channels": {"p_commit": 0.1, "p_action": 0.1},
    }

    results = {}
    for name, s in scenarios.items():
        p_forgery = s["p_commit"] * s["p_action"] * p_within
        # Bits of security: -log2(p_forgery)
        bits = -math.log2(p_forgery) if p_forgery > 0 else float("inf")
        results[name] = {
            "p_forgery": f"{p_forgery:.2e}",
            "security_bits": round(bits, 1),
        }

    return {
        "window_seconds": window_seconds,
        "window_human": f"{window_seconds/60:.1f}min" if window_seconds >= 60 else f"{window_seconds}s",
        "reference_mmd": "86400s (CT standard)",
        "p_within_window": round(p_within, 6),
        "scenarios": results,
        "recommendation": (
            "TIGHT" if window_seconds <= 300 else
            "MODERATE" if window_seconds <= 3600 else
            "LOOSE" if window_seconds <= 86400 else
            "DANGEROUS"
        ),
        "note": "Shorter window = harder forgery = higher latency. Design the tradeoff explicitly.",
    }


def main():
    parser = argparse.ArgumentParser(description="Pre-commitment hash verifier (Ulysses pattern)")
    sub = parser.add_subparsers(dest="command", required=True)

    # commit
    p_commit = sub.add_parser("commit", help="Create a pre-commitment hash")
    p_commit.add_argument("--intent", required=True, help="Action you intend to take")
    p_commit.add_argument("--nonce", default="", help="Optional nonce for hiding intent")

    # verify
    p_verify = sub.add_parser("verify", help="Verify pre-commitment against actual")
    p_verify.add_argument("--hash", required=True, help="Previously committed hash")
    p_verify.add_argument("--actual", required=True, help="Actual action taken")
    p_verify.add_argument("--nonce", default="", help="Nonce used during commit")
    p_verify.add_argument("--committed-at", help="ISO8601 timestamp of commitment")
    p_verify.add_argument("--max-window", type=float, default=86400, help="Max valid window (seconds)")

    # analyze-window
    p_window = sub.add_parser("analyze-window", help="Analyze commit window security")
    p_window.add_argument("--window-seconds", type=float, required=True)

    args = parser.parse_args()

    if args.command == "commit":
        result = commit_hash(args.intent, args.nonce)
    elif args.command == "verify":
        result = verify(args.hash, args.actual, args.nonce, args.committed_at, args.max_window)
    elif args.command == "analyze-window":
        result = analyze_window(args.window_seconds)

    json.dump(result, sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
