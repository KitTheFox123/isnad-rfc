#!/usr/bin/env python3
"""intent-commit.py — Intent commitment before execution (L2→L3 bridge).

An agent commits to its intended actions BEFORE executing them,
creating a verifiable record that can be audited post-hoc.

Based on Gollwitzer (1999) implementation intentions:
"I will do X when situation Y arises" → pre-committed, falsifiable.

Flow:
  1. Agent declares intent (action + scope + expected outcome)
  2. Intent is hashed and timestamped (commitment)
  3. Agent executes
  4. Outcome is compared against commitment (verification)

The gap between commitment and execution is the TOCTOU window
(Lilienthal & Hong, arXiv 2508.17155). Smaller gap = less attack surface.
CT-style logging makes the gap auditable.

References:
  - Gollwitzer (1999) Implementation Intentions
  - Lilienthal & Hong (2508.17155) TOCTOU in LLM Agents
  - RFC 9162 Certificate Transparency v2
  - humanrootoftrust.org — Human Root of Trust framework
"""

import hashlib
import json
import time
import sys
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class IntentCommitment:
    agent_id: str
    action: str
    scope: str  # What the agent is authorized to do
    expected_outcome: str
    timestamp: float
    principal: str  # Human who authorized this scope
    ttl_seconds: int = 300  # 5 min default — short-lived
    nonce: str = ""

    def __post_init__(self):
        if not self.nonce:
            self.nonce = hashlib.sha256(
                f"{self.agent_id}{self.timestamp}{self.action}".encode()
            ).hexdigest()[:16]

    def commitment_hash(self) -> str:
        """Hash the intent for append-only log inclusion."""
        payload = json.dumps(asdict(self), sort_keys=True).encode()
        return hashlib.sha256(payload).hexdigest()

    def is_expired(self) -> bool:
        return time.time() > self.timestamp + self.ttl_seconds


@dataclass
class ExecutionRecord:
    commitment_hash: str
    actual_outcome: str
    execution_timestamp: float
    success: bool

    def drift_seconds(self, commit_time: float) -> float:
        """TOCTOU gap: time between commitment and execution."""
        return self.execution_timestamp - commit_time


class IntentLog:
    """Append-only intent log (CT-style, no deletions)."""

    def __init__(self):
        self.commitments: list[IntentCommitment] = []
        self.executions: dict[str, ExecutionRecord] = {}
        self.merkle_leaves: list[str] = []

    def commit(self, intent: IntentCommitment) -> str:
        """Record intent commitment. Returns commitment hash."""
        h = intent.commitment_hash()
        self.commitments.append(intent)
        self.merkle_leaves.append(h)
        return h

    def record_execution(self, commitment_hash: str, outcome: str, success: bool) -> Optional[ExecutionRecord]:
        """Record execution against a prior commitment."""
        # Find the commitment
        matching = [c for c in self.commitments if c.commitment_hash() == commitment_hash]
        if not matching:
            return None

        commit = matching[0]
        if commit.is_expired():
            print(f"WARNING: commitment {commitment_hash[:12]}... expired "
                  f"({time.time() - commit.timestamp - commit.ttl_seconds:.1f}s ago)")

        record = ExecutionRecord(
            commitment_hash=commitment_hash,
            actual_outcome=outcome,
            execution_timestamp=time.time(),
            success=success,
        )
        self.executions[commitment_hash] = record
        return record

    def audit(self) -> dict:
        """Audit the log for anomalies."""
        total = len(self.commitments)
        executed = len(self.executions)
        expired_unexecuted = sum(
            1 for c in self.commitments
            if c.is_expired() and c.commitment_hash() not in self.executions
        )
        avg_gap = 0.0
        if self.executions:
            gaps = [
                e.drift_seconds(c.timestamp)
                for c in self.commitments
                for e in [self.executions.get(c.commitment_hash())]
                if e is not None
            ]
            avg_gap = sum(gaps) / len(gaps) if gaps else 0.0

        outcome_mismatches = sum(
            1 for c in self.commitments
            if c.commitment_hash() in self.executions
            and self.executions[c.commitment_hash()].actual_outcome != c.expected_outcome
        )

        return {
            "total_commitments": total,
            "executed": executed,
            "unexecuted": total - executed,
            "expired_unexecuted": expired_unexecuted,
            "outcome_mismatches": outcome_mismatches,
            "avg_toctou_gap_seconds": round(avg_gap, 3),
            "merkle_root": self._merkle_root(),
        }

    def _merkle_root(self) -> str:
        """Compute Merkle root of all commitment hashes."""
        if not self.merkle_leaves:
            return hashlib.sha256(b"empty").hexdigest()
        leaves = list(self.merkle_leaves)
        while len(leaves) > 1:
            if len(leaves) % 2:
                leaves.append(leaves[-1])
            leaves = [
                hashlib.sha256((leaves[i] + leaves[i + 1]).encode()).hexdigest()
                for i in range(0, len(leaves), 2)
            ]
        return leaves[0]


def demo():
    """Run a demo scenario."""
    log = IntentLog()

    # Agent commits to checking email
    intent1 = IntentCommitment(
        agent_id="kit_fox",
        action="check_email",
        scope="read inbox, reply to known contacts",
        expected_outcome="inbox checked, 0-3 replies sent",
        timestamp=time.time(),
        principal="ilya",
        ttl_seconds=300,
    )
    h1 = log.commit(intent1)
    print(f"Committed: check_email → {h1[:16]}...")

    # Agent commits to posting on Clawk
    intent2 = IntentCommitment(
        agent_id="kit_fox",
        action="clawk_post",
        scope="post to @Kit_Fox, max 280 chars, no DMs",
        expected_outcome="1 post published",
        timestamp=time.time(),
        principal="ilya",
        ttl_seconds=120,
    )
    h2 = log.commit(intent2)
    print(f"Committed: clawk_post → {h2[:16]}...")

    # Execute
    time.sleep(0.1)  # Simulate work
    log.record_execution(h1, "inbox checked, 0-3 replies sent", True)
    log.record_execution(h2, "1 post published", True)

    # Audit
    audit = log.audit()
    print(f"\nAudit: {json.dumps(audit, indent=2)}")

    # Expired commitment (simulated)
    intent3 = IntentCommitment(
        agent_id="kit_fox",
        action="research_post",
        scope="search keenable, write moltbook post",
        expected_outcome="1 research post",
        timestamp=time.time() - 400,  # Already expired
        principal="ilya",
        ttl_seconds=300,
    )
    h3 = log.commit(intent3)
    log.record_execution(h3, "1 research post", True)

    audit2 = log.audit()
    print(f"\nPost-expired audit: {json.dumps(audit2, indent=2)}")
    return audit2["outcome_mismatches"] == 0 and audit2["total_commitments"] == 3


if __name__ == "__main__":
    success = demo()
    sys.exit(0 if success else 1)
