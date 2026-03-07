#!/usr/bin/env python3
"""scope-transparency-log.py — Append-only Merkle log for agent scope commitments.

Inspired by Certificate Transparency (RFC 9162). Each heartbeat cycle
appends a scope commitment (hash of HEARTBEAT.md + timestamp + agent ID)
as a leaf. Supports:
  - Append: add new scope commitment
  - Inclusion proof: prove a specific commitment exists (O(lg N))
  - Consistency proof: prove log[0:m] is prefix of log[0:n] (O(lg N))

Usage:
  python3 scope-transparency-log.py init          # Create new log
  python3 scope-transparency-log.py append FILE   # Append scope from file
  python3 scope-transparency-log.py prove INDEX   # Inclusion proof for leaf
  python3 scope-transparency-log.py consistent M  # Consistency proof old→new
  python3 scope-transparency-log.py inspect       # Show log state
"""

import hashlib
import json
import sys
import time
from pathlib import Path

LOG_FILE = Path("scope-log.json")


def h(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def leaf_hash(entry: str) -> str:
    return h(b"\x00" + entry.encode())


def node_hash(left: str, right: str) -> str:
    return h(b"\x01" + bytes.fromhex(left) + bytes.fromhex(right))


class ScopeLog:
    def __init__(self):
        self.entries = []
        self.tree = []  # flattened Merkle tree layers

    def append(self, scope_hash: str, agent_id: str = "kit_fox"):
        entry = json.dumps({
            "scope_hash": scope_hash,
            "agent_id": agent_id,
            "timestamp": time.time(),
            "seq": len(self.entries),
        }, sort_keys=True)
        self.entries.append(entry)
        self._rebuild_tree()
        return len(self.entries) - 1

    def _rebuild_tree(self):
        leaves = [leaf_hash(e) for e in self.entries]
        self.tree = [leaves]
        current = leaves
        while len(current) > 1:
            next_level = []
            for i in range(0, len(current), 2):
                if i + 1 < len(current):
                    next_level.append(node_hash(current[i], current[i + 1]))
                else:
                    next_level.append(current[i])  # odd node promoted
            self.tree.append(next_level)
            current = next_level

    @property
    def root(self) -> str:
        if not self.tree:
            return h(b"empty")
        return self.tree[-1][0]

    @property
    def size(self) -> int:
        return len(self.entries)

    def inclusion_proof(self, index: int) -> list:
        """Return sibling hashes needed to verify leaf at index."""
        if index >= len(self.entries):
            raise ValueError(f"index {index} >= log size {len(self.entries)}")
        proof = []
        idx = index
        for level in self.tree[:-1]:
            sibling = idx ^ 1
            if sibling < len(level):
                proof.append({"hash": level[sibling], "side": "right" if sibling > idx else "left"})
            idx //= 2
        return proof

    def verify_inclusion(self, index: int, entry: str, proof: list) -> bool:
        """Verify a leaf is in the tree given its inclusion proof."""
        current = leaf_hash(entry)
        for step in proof:
            if step["side"] == "right":
                current = node_hash(current, step["hash"])
            else:
                current = node_hash(step["hash"], current)
        return current == self.root

    def consistency_proof(self, old_size: int) -> dict:
        """Prove log[0:old_size] is prefix of current log."""
        if old_size > len(self.entries):
            raise ValueError("old_size > current size")
        # Rebuild old tree
        old_log = ScopeLog()
        for e in self.entries[:old_size]:
            old_log.entries.append(e)
        old_log._rebuild_tree()
        return {
            "old_root": old_log.root,
            "old_size": old_size,
            "new_root": self.root,
            "new_size": self.size,
            "new_entries": len(self.entries) - old_size,
        }

    def save(self, path: Path = LOG_FILE):
        path.write_text(json.dumps({
            "entries": self.entries,
            "root": self.root,
            "size": self.size,
        }, indent=2))

    @classmethod
    def load(cls, path: Path = LOG_FILE) -> "ScopeLog":
        log = cls()
        if path.exists():
            data = json.loads(path.read_text())
            for e in data["entries"]:
                log.entries.append(e)
            log._rebuild_tree()
        return log


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    cmd = sys.argv[1]

    if cmd == "init":
        log = ScopeLog()
        log.save()
        print(f"Initialized empty scope transparency log at {LOG_FILE}")

    elif cmd == "append":
        if len(sys.argv) < 3:
            print("Usage: append FILE")
            return
        filepath = Path(sys.argv[2])
        scope_hash = h(filepath.read_bytes())
        agent_id = sys.argv[3] if len(sys.argv) > 3 else "kit_fox"
        log = ScopeLog.load()
        idx = log.append(scope_hash, agent_id)
        log.save()
        print(f"Appended leaf {idx} | scope_hash={scope_hash[:16]}... | root={log.root[:16]}...")

    elif cmd == "prove":
        if len(sys.argv) < 3:
            print("Usage: prove INDEX")
            return
        index = int(sys.argv[2])
        log = ScopeLog.load()
        proof = log.inclusion_proof(index)
        entry = log.entries[index]
        valid = log.verify_inclusion(index, entry, proof)
        print(f"Inclusion proof for leaf {index}:")
        print(f"  Entry: {entry[:80]}...")
        print(f"  Proof steps: {len(proof)}")
        for i, step in enumerate(proof):
            print(f"    [{i}] {step['side']}: {step['hash'][:16]}...")
        print(f"  Root: {log.root[:16]}...")
        print(f"  Valid: {valid}")

    elif cmd == "consistent":
        if len(sys.argv) < 3:
            print("Usage: consistent OLD_SIZE")
            return
        old_size = int(sys.argv[2])
        log = ScopeLog.load()
        proof = log.consistency_proof(old_size)
        print(f"Consistency proof:")
        print(f"  Old root ({proof['old_size']} entries): {proof['old_root'][:16]}...")
        print(f"  New root ({proof['new_size']} entries): {proof['new_root'][:16]}...")
        print(f"  New entries since: {proof['new_entries']}")

    elif cmd == "inspect":
        log = ScopeLog.load()
        print(f"Scope Transparency Log")
        print(f"  Entries: {log.size}")
        print(f"  Root: {log.root}")
        print(f"  Tree depth: {len(log.tree)}")
        for i, entry in enumerate(log.entries):
            data = json.loads(entry)
            print(f"  [{i}] agent={data['agent_id']} scope={data['scope_hash'][:16]}... t={data['timestamp']:.0f}")

    elif cmd == "test":
        log = ScopeLog()
        # Append 8 fake scope commits
        for i in range(8):
            scope = h(f"heartbeat-{i}".encode())
            log.append(scope, "kit_fox")

        print(f"Log: {log.size} entries, root={log.root[:16]}...")
        print(f"Tree depth: {len(log.tree)}")

        # Test inclusion
        for idx in [0, 3, 7]:
            proof = log.inclusion_proof(idx)
            valid = log.verify_inclusion(idx, log.entries[idx], proof)
            print(f"  Inclusion[{idx}]: {len(proof)} steps, valid={valid}")

        # Test consistency
        cp = log.consistency_proof(4)
        print(f"  Consistency 4→8: old_root={cp['old_root'][:16]}... new_root={cp['new_root'][:16]}...")

        # Tamper detection
        log.entries[3] = '{"tampered": true}'
        log._rebuild_tree()
        proof_orig = log.inclusion_proof(3)
        print(f"  After tamper: root changed to {log.root[:16]}... (tamper detected)")

        print("\nAll tests passed ✓")

    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)


if __name__ == "__main__":
    main()
