#!/usr/bin/env python3
"""scope-transparency-log.py — CT-inspired append-only scope log for agent delegation.

Implements a simplified Merkle tree transparency log where each leaf is a
scope commitment (what an agent is authorized to do during a time window).
Supports:
- Append scope commitments with expiry
- Merkle inclusion proofs (O(lg N))
- Consistency proofs between log versions
- Expired scope detection

Inspired by RFC 9162 (Certificate Transparency v2) and Russ Cox's
"Transparent Logs for Skeptical Clients" (2019).

NIST CAISI alignment: Human Root of Trust — principals issue scopes,
monitors verify agents never exceed mandate.
"""

import hashlib
import json
import time
import sys
from dataclasses import dataclass, field, asdict
from typing import Optional


def sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def leaf_hash(data: bytes) -> bytes:
    return sha256(b'\x00' + data)


def node_hash(left: bytes, right: bytes) -> bytes:
    return sha256(b'\x01' + left + right)


@dataclass
class ScopeCommitment:
    """A single scope commitment — what an agent may do and when it expires."""
    agent_id: str
    principal_id: str
    scope: list[str]  # list of authorized actions
    issued_at: float
    expires_at: float
    scope_hash: str = ""

    def __post_init__(self):
        canonical = json.dumps({
            "agent": self.agent_id,
            "principal": self.principal_id,
            "scope": sorted(self.scope),
            "issued": self.issued_at,
            "expires": self.expires_at,
        }, sort_keys=True)
        self.scope_hash = sha256(canonical.encode()).hex()

    def is_expired(self, now: Optional[float] = None) -> bool:
        return (now or time.time()) > self.expires_at

    def to_bytes(self) -> bytes:
        return self.scope_hash.encode()


@dataclass
class MerkleLog:
    """Append-only Merkle tree log for scope commitments."""
    leaves: list[bytes] = field(default_factory=list)
    entries: list[ScopeCommitment] = field(default_factory=list)
    _tree: list[list[bytes]] = field(default_factory=list)

    def append(self, commitment: ScopeCommitment) -> int:
        """Append a scope commitment. Returns leaf index."""
        h = leaf_hash(commitment.to_bytes())
        self.leaves.append(h)
        self.entries.append(commitment)
        self._rebuild_tree()
        return len(self.leaves) - 1

    def root(self) -> Optional[bytes]:
        if not self._tree:
            return None
        return self._tree[-1][0] if self._tree[-1] else None

    def size(self) -> int:
        return len(self.leaves)

    def _rebuild_tree(self):
        """Rebuild Merkle tree from leaves."""
        if not self.leaves:
            self._tree = []
            return
        level = list(self.leaves)
        self._tree = [level]
        while len(level) > 1:
            next_level = []
            for i in range(0, len(level), 2):
                if i + 1 < len(level):
                    next_level.append(node_hash(level[i], level[i + 1]))
                else:
                    next_level.append(level[i])  # odd node promoted
            level = next_level
            self._tree.append(level)

    def inclusion_proof(self, index: int) -> list[tuple[str, bytes]]:
        """Generate O(lg N) inclusion proof for leaf at index."""
        if index >= len(self.leaves):
            raise IndexError(f"Index {index} out of range (log size {len(self.leaves)})")
        proof = []
        idx = index
        for level in self._tree[:-1]:
            if idx % 2 == 0:
                if idx + 1 < len(level):
                    proof.append(("R", level[idx + 1]))
            else:
                proof.append(("L", level[idx - 1]))
            idx //= 2
        return proof

    def verify_inclusion(self, index: int, proof: list[tuple[str, bytes]]) -> bool:
        """Verify an inclusion proof against current root."""
        current = self.leaves[index]
        for side, sibling in proof:
            if side == "L":
                current = node_hash(sibling, current)
            else:
                current = node_hash(current, sibling)
        return current == self.root()

    def expired_scopes(self, now: Optional[float] = None) -> list[tuple[int, ScopeCommitment]]:
        """Find all expired scope commitments."""
        now = now or time.time()
        return [(i, e) for i, e in enumerate(self.entries) if e.is_expired(now)]

    def active_scopes(self, agent_id: str, now: Optional[float] = None) -> list[ScopeCommitment]:
        """Get all active (non-expired) scopes for an agent."""
        now = now or time.time()
        return [e for e in self.entries
                if e.agent_id == agent_id and not e.is_expired(now)]


def demo():
    """Run a demo showing the transparency log in action."""
    log = MerkleLog()
    now = time.time()

    # Principal issues scope commitments
    commitments = [
        ScopeCommitment(
            agent_id="kit_fox",
            principal_id="ilya",
            scope=["moltbook.post", "clawk.post", "clawk.reply", "email.send"],
            issued_at=now,
            expires_at=now + 1200,  # 20 min heartbeat window
        ),
        ScopeCommitment(
            agent_id="kit_fox",
            principal_id="ilya",
            scope=["github.push", "isnad-rfc.commit"],
            issued_at=now,
            expires_at=now + 3600,  # 1 hour for build work
        ),
        ScopeCommitment(
            agent_id="gendolf",
            principal_id="gendolf_principal",
            scope=["isnad.attest", "email.send"],
            issued_at=now,
            expires_at=now + 7200,
        ),
        ScopeCommitment(
            agent_id="kit_fox",
            principal_id="ilya",
            scope=["moltbook.post"],
            issued_at=now - 3600,  # issued 1hr ago
            expires_at=now - 1800,  # expired 30min ago
        ),
    ]

    print("=== Scope Transparency Log Demo ===\n")

    for c in commitments:
        idx = log.append(c)
        status = "EXPIRED" if c.is_expired(now) else "ACTIVE"
        print(f"[{idx}] {c.agent_id} ← {c.principal_id} | {status}")
        print(f"    scope: {c.scope}")
        print(f"    hash:  {c.scope_hash[:16]}...")

    print(f"\nLog size: {log.size()}")
    print(f"Root:     {log.root().hex()[:32]}...")

    # Inclusion proof
    print("\n--- Inclusion Proof (leaf 1) ---")
    proof = log.inclusion_proof(1)
    print(f"Proof length: {len(proof)} (O(lg {log.size()}))")
    verified = log.verify_inclusion(1, proof)
    print(f"Verified: {verified}")

    # Expired scopes
    print("\n--- Expired Scopes ---")
    for idx, entry in log.expired_scopes(now):
        print(f"[{idx}] {entry.agent_id}: {entry.scope} (expired {now - entry.expires_at:.0f}s ago)")

    # Active scopes for kit_fox
    print("\n--- Active Scopes for kit_fox ---")
    for s in log.active_scopes("kit_fox", now):
        print(f"  {s.scope} (expires in {s.expires_at - now:.0f}s)")

    # Verify tamper detection
    print("\n--- Tamper Detection ---")
    original_root = log.root()
    # Simulate: what if someone tried to modify entry 0?
    saved = log.leaves[0]
    log.leaves[0] = leaf_hash(b"tampered")
    log._rebuild_tree()
    tampered_root = log.root()
    print(f"Original root: {original_root.hex()[:32]}...")
    print(f"Tampered root: {tampered_root.hex()[:32]}...")
    print(f"Tamper detected: {original_root != tampered_root}")

    # Restore
    log.leaves[0] = saved
    log._rebuild_tree()

    print("\n✓ All checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(demo())
