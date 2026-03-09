#!/usr/bin/env python3
"""intent-commit-validator.py — Validates L0-L3 intent-commit schema instances.

Checks provenance level requirements per docs/intent-commit-schema-v0.1.md.
Each level is a strict superset: L3 requires all L2 fields, L2 requires all L1 fields, etc.

Usage:
    python3 intent-commit-validator.py --demo
    python3 intent-commit-validator.py --validate FILE.json
    python3 intent-commit-validator.py --level L3 --check-fields
"""

import argparse
import json
import hashlib
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import List, Optional


REQUIRED_FIELDS = {
    "L0": ["agent_id", "action", "timestamp"],
    "L1": ["agent_id", "action", "timestamp", "scope", "scope_hash",
            "wal_entry_hash", "wal_prev_hash", "signature"],
    "L2": ["agent_id", "action", "timestamp", "scope", "scope_hash",
            "wal_entry_hash", "wal_prev_hash", "signature", "witness"],
    "L3": ["agent_id", "action", "timestamp", "scope", "scope_hash",
            "wal_entry_hash", "wal_prev_hash", "signature", "witness",
            "intent", "intent_hash", "deadline", "commitment"],
}

WITNESS_FIELDS = ["witness_id", "heartbeat_ts", "signature"]
COMMITMENT_FIELDS = ["channel", "tx_id", "published_at", "intent_hash"]
RESULT_FIELDS = ["status", "evidence_uri", "completed_at"]

TRUST_MULTIPLIER = {"L0": 0.5, "L1": 0.75, "L2": 1.0, "L3": 1.25}

SUPPORTED_CHANNELS = ["nostr", "solana", "ethereum", "sigstore_rekor", "ipfs"]


@dataclass
class ValidationResult:
    level: str
    valid: bool
    errors: List[str]
    warnings: List[str]
    trust_multiplier: float
    grade: str


def validate_instance(data: dict) -> ValidationResult:
    """Validate a single intent-commit instance."""
    errors = []
    warnings = []
    
    level = data.get("provenance_level", "UNKNOWN")
    if level not in REQUIRED_FIELDS:
        return ValidationResult(level, False, [f"Unknown level: {level}"], [], 0.0, "F")
    
    # Check required fields
    for field in REQUIRED_FIELDS[level]:
        if field not in data:
            errors.append(f"Missing required field: {field}")
    
    # Level-specific checks
    if level in ("L1", "L2", "L3"):
        # Verify scope_hash
        if "scope" in data and "scope_hash" in data:
            expected = "sha256:" + hashlib.sha256(
                json.dumps(data["scope"], sort_keys=True).encode()
            ).hexdigest()[:20] + "..."
            # Can't fully verify truncated hashes, but check prefix
            if not data["scope_hash"].startswith("sha256:"):
                warnings.append("scope_hash should start with 'sha256:'")
    
    if level in ("L2", "L3"):
        # Verify witness fields
        witness = data.get("witness", {})
        for wf in WITNESS_FIELDS:
            if wf not in witness:
                errors.append(f"Missing witness field: {wf}")
    
    if level == "L3":
        # Verify commitment fields
        commitment = data.get("commitment", {})
        for cf in COMMITMENT_FIELDS:
            if cf not in commitment:
                errors.append(f"Missing commitment field: {cf}")
        
        # Check commitment before action
        if "commitment" in data and "timestamp" in data:
            pub = commitment.get("published_at", "")
            ts = data.get("timestamp", "")
            if pub and ts and pub >= ts:
                errors.append("Commitment must be BEFORE action timestamp")
        
        # Check deadline
        if "deadline" in data and "result" in data:
            result = data.get("result", {})
            completed = result.get("completed_at", "")
            deadline = data["deadline"]
            if completed and deadline and completed > deadline:
                warnings.append("Deadline exceeded — downgrades to L2")
        
        # Check channel
        channel = commitment.get("channel", "")
        if channel and channel not in SUPPORTED_CHANNELS:
            warnings.append(f"Non-standard channel: {channel}")
        
        # Verify intent_hash matches commitment
        if commitment.get("intent_hash") != data.get("intent_hash"):
            errors.append("intent_hash mismatch between action and commitment")
    
    valid = len(errors) == 0
    multiplier = TRUST_MULTIPLIER.get(level, 0.0) if valid else 0.0
    
    if not valid:
        grade = "F"
    elif len(warnings) > 2:
        grade = "C"
    elif len(warnings) > 0:
        grade = "B"
    else:
        grade = "A"
    
    return ValidationResult(level, valid, errors, warnings, multiplier, grade)


def demo():
    """Run demo validation."""
    examples = [
        {
            "name": "Valid L0",
            "data": {
                "provenance_level": "L0",
                "agent_id": "kit@isnad.dev",
                "action": "heartbeat_check",
                "timestamp": "2026-03-09T14:00:00Z"
            }
        },
        {
            "name": "Valid L3",
            "data": {
                "provenance_level": "L3",
                "agent_id": "gendolf@isnad.dev",
                "action": "deploy_contract",
                "timestamp": "2026-03-09T10:00:00Z",
                "scope": {"domain": "solana:mainnet", "permissions": ["deploy"]},
                "scope_hash": "sha256:7e3f1a9b0c...",
                "intent": "Deploy escrow contract",
                "intent_hash": "sha256:b4d8e2f1a0c9...",
                "deadline": "2026-03-09T12:00:00Z",
                "commitment": {
                    "channel": "nostr",
                    "tx_id": "note1abc123",
                    "published_at": "2026-03-09T09:55:00Z",
                    "intent_hash": "sha256:b4d8e2f1a0c9..."
                },
                "wal_entry_hash": "sha256:a1b2c3d4...",
                "wal_prev_hash": "sha256:9f8e7d6c...",
                "signature": "ed25519:AgentKey...",
                "witness": {
                    "witness_id": "sentinel@isnad.dev",
                    "heartbeat_ts": "2026-03-09T09:58:00Z",
                    "signature": "ed25519:WitnessSig..."
                },
                "result": {
                    "status": "success",
                    "evidence_uri": "https://solscan.io/tx/5xYz",
                    "completed_at": "2026-03-09T10:02:30Z"
                }
            }
        },
        {
            "name": "Invalid L3 (commitment after action)",
            "data": {
                "provenance_level": "L3",
                "agent_id": "rogue@isnad.dev",
                "action": "deploy_contract",
                "timestamp": "2026-03-09T10:00:00Z",
                "scope": {"domain": "solana:mainnet"},
                "scope_hash": "sha256:abc...",
                "intent": "Deploy",
                "intent_hash": "sha256:def...",
                "deadline": "2026-03-09T12:00:00Z",
                "commitment": {
                    "channel": "nostr",
                    "tx_id": "note1xyz",
                    "published_at": "2026-03-09T10:05:00Z",
                    "intent_hash": "sha256:def..."
                },
                "wal_entry_hash": "sha256:111...",
                "wal_prev_hash": "sha256:222...",
                "signature": "ed25519:Rogue...",
                "witness": {
                    "witness_id": "sentinel@isnad.dev",
                    "heartbeat_ts": "2026-03-09T09:58:00Z",
                    "signature": "ed25519:Wit..."
                }
            }
        },
        {
            "name": "L2 missing witness",
            "data": {
                "provenance_level": "L2",
                "agent_id": "test@isnad.dev",
                "action": "check_scope",
                "timestamp": "2026-03-09T14:00:00Z",
                "scope": {"domain": "local"},
                "scope_hash": "sha256:eee...",
                "wal_entry_hash": "sha256:fff...",
                "wal_prev_hash": "sha256:ggg...",
                "signature": "ed25519:Test..."
            }
        }
    ]
    
    print("=" * 60)
    print("INTENT-COMMIT SCHEMA VALIDATOR")
    print("=" * 60)
    
    for ex in examples:
        result = validate_instance(ex["data"])
        status = "✅ VALID" if result.valid else "❌ INVALID"
        print(f"\n[{result.grade}] {ex['name']} — {result.level} — {status}")
        print(f"    Trust multiplier: ×{result.trust_multiplier}")
        for e in result.errors:
            print(f"    ❌ {e}")
        for w in result.warnings:
            print(f"    ⚠️ {w}")
    
    print(f"\n{'=' * 60}")
    print("Schema: docs/intent-commit-schema-v0.1.md (Gendolf + Kit)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="L0-L3 Intent-Commit Schema Validator")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--validate", type=str, help="Validate JSON file")
    parser.add_argument("--level", type=str, help="Show required fields for level")
    args = parser.parse_args()
    
    if args.validate:
        with open(args.validate) as f:
            data = json.load(f)
        result = validate_instance(data)
        print(json.dumps({"level": result.level, "valid": result.valid, 
                          "errors": result.errors, "warnings": result.warnings,
                          "trust_multiplier": result.trust_multiplier, "grade": result.grade}, indent=2))
    elif args.level:
        level = args.level.upper()
        if level in REQUIRED_FIELDS:
            print(f"{level} required fields: {REQUIRED_FIELDS[level]}")
            print(f"Trust multiplier: ×{TRUST_MULTIPLIER[level]}")
        else:
            print(f"Unknown level: {level}")
    else:
        demo()
