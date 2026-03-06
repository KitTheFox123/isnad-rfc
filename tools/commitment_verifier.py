#!/usr/bin/env python3
"""commitment_verifier.py — Verify scope commitment binding.

Maps agent scope lifecycle to cryptographic commitment scheme phases:
  1. COMMIT: Hash scope at issuance (binding)
  2. ACTION: Agent acts within scope window
  3. REVEAL: Open commitment, verify action matched scope

Inspired by Brassard/Chaum/Crépeau 1988 commitment formalization
and CT log SCT (Signed Certificate Timestamp) model.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ScopeCommitment:
    """A committed scope with binding properties."""
    scope_text: str
    commit_hash: str
    committed_at: float
    ttl_seconds: float
    principal: str
    nonce: str = ""
    
    @property
    def expired(self) -> bool:
        return time.time() > self.committed_at + self.ttl_seconds
    
    @property
    def remaining_seconds(self) -> float:
        return max(0, (self.committed_at + self.ttl_seconds) - time.time())


@dataclass
class ActionRecord:
    """An action taken during a scope window."""
    action_type: str
    description: str
    timestamp: float
    scope_hash_at_action: str  # commit hash agent saw


@dataclass
class RevealResult:
    """Result of opening a commitment."""
    binding_valid: bool  # scope wasn't changed
    timing_valid: bool   # action within TTL
    chain_valid: bool    # action referenced correct commit
    grade: str
    details: list = field(default_factory=list)


def commit_scope(scope_text: str, principal: str, ttl_seconds: float = 1200.0) -> ScopeCommitment:
    """Phase 1: Commit to a scope. Returns binding commitment."""
    nonce = hashlib.sha256(f"{time.time()}{principal}".encode()).hexdigest()[:16]
    commit_input = f"{scope_text}|{principal}|{nonce}"
    commit_hash = hashlib.sha256(commit_input.encode()).hexdigest()
    
    return ScopeCommitment(
        scope_text=scope_text,
        commit_hash=commit_hash,
        committed_at=time.time(),
        ttl_seconds=ttl_seconds,
        principal=principal,
        nonce=nonce,
    )


def record_action(commitment: ScopeCommitment, action_type: str, description: str) -> ActionRecord:
    """Phase 2: Record an action that references the current commitment."""
    return ActionRecord(
        action_type=action_type,
        description=description,
        timestamp=time.time(),
        scope_hash_at_action=commitment.commit_hash,
    )


def reveal_and_verify(
    commitment: ScopeCommitment,
    action: ActionRecord,
    revealed_scope: str,
    revealed_nonce: str,
    revealed_principal: str,
) -> RevealResult:
    """Phase 3: Open commitment and verify action was within scope."""
    details = []
    
    # Check binding: recompute hash from revealed values
    recomputed = hashlib.sha256(
        f"{revealed_scope}|{revealed_principal}|{revealed_nonce}".encode()
    ).hexdigest()
    binding_valid = recomputed == commitment.commit_hash
    if not binding_valid:
        details.append("BINDING FAILURE: revealed scope doesn't match commitment")
    else:
        details.append("Binding valid: scope unchanged since commit")
    
    # Check timing: action within TTL
    action_offset = action.timestamp - commitment.committed_at
    timing_valid = 0 <= action_offset <= commitment.ttl_seconds
    if not timing_valid:
        details.append(f"TIMING FAILURE: action at +{action_offset:.1f}s, TTL={commitment.ttl_seconds}s")
    else:
        details.append(f"Timing valid: action at +{action_offset:.1f}s within {commitment.ttl_seconds}s TTL")
    
    # Check chain: action referenced correct commit
    chain_valid = action.scope_hash_at_action == commitment.commit_hash
    if not chain_valid:
        details.append("CHAIN FAILURE: action referenced different commitment")
    else:
        details.append("Chain valid: action referenced correct commitment")
    
    # Grade
    score = sum([binding_valid, timing_valid, chain_valid])
    grade = {3: "A", 2: "B", 1: "D", 0: "F"}[score]
    
    return RevealResult(
        binding_valid=binding_valid,
        timing_valid=timing_valid,
        chain_valid=chain_valid,
        grade=grade,
        details=details,
    )


def demo():
    """Run a complete commit-act-reveal cycle."""
    print("=== Commitment Verifier Demo ===\n")
    
    # Phase 1: Commit
    scope = "Check Clawk notifications, reply to mentions, post 1 research thread"
    commitment = commit_scope(scope, principal="ilya", ttl_seconds=1200)
    print(f"COMMIT: {commitment.commit_hash[:16]}...")
    print(f"  Scope: {scope}")
    print(f"  TTL: {commitment.ttl_seconds}s")
    print(f"  Principal: {commitment.principal}\n")
    
    # Phase 2: Act
    actions = [
        record_action(commitment, "clawk_reply", "Replied to santaclawd on commitment schemes"),
        record_action(commitment, "clawk_reply", "Replied to drift investigation thread"),
        record_action(commitment, "clawk_post", "Posted binding/hiding tradeoff observation"),
    ]
    print(f"ACTIONS: {len(actions)} recorded")
    for a in actions:
        print(f"  [{a.action_type}] {a.description}")
    print()
    
    # Phase 3: Reveal and verify
    print("REVEAL & VERIFY:")
    for i, action in enumerate(actions):
        result = reveal_and_verify(
            commitment, action,
            revealed_scope=scope,
            revealed_nonce=commitment.nonce,
            revealed_principal="ilya",
        )
        print(f"  Action {i+1}: Grade {result.grade}")
        for d in result.details:
            print(f"    {d}")
    
    # Demonstrate binding failure
    print("\n--- Binding Failure Demo ---")
    tampered = reveal_and_verify(
        commitment, actions[0],
        revealed_scope="DIFFERENT SCOPE that wasn't committed",
        revealed_nonce=commitment.nonce,
        revealed_principal="ilya",
    )
    print(f"  Tampered reveal: Grade {tampered.grade}")
    for d in tampered.details:
        print(f"    {d}")


if __name__ == "__main__":
    demo()
