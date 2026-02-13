#!/usr/bin/env python3
"""
isnad — Reference implementation of Isnad Chains for Agent Reputation
Based on RFC: github.com/KitTheFox123/isnad-rfc

Core module: keypairs, attestations, chain validation.
"""

import json
import time
import hashlib
import os
from datetime import datetime, timezone
from typing import Optional

from nacl.signing import SigningKey, VerifyKey
from nacl.encoding import HexEncoder
from nacl.exceptions import BadSignatureError


# ─── Identity ──────────────────────────────────────────────────────

class AgentIdentity:
    """Ed25519 keypair for an agent."""
    
    def __init__(self, signing_key: Optional[SigningKey] = None):
        self.signing_key = signing_key or SigningKey.generate()
        self.verify_key = self.signing_key.verify_key
    
    @property
    def agent_id(self) -> str:
        """Derive agent ID from public key hash."""
        pubkey_hex = self.verify_key.encode(encoder=HexEncoder).decode()
        return f"agent:{hashlib.sha256(pubkey_hex.encode()).hexdigest()[:16]}"
    
    @property
    def public_key_hex(self) -> str:
        return self.verify_key.encode(encoder=HexEncoder).decode()
    
    def sign(self, data: bytes) -> bytes:
        """Sign data with private key."""
        return self.signing_key.sign(data).signature
    
    def export_keys(self) -> dict:
        """Export keypair for storage."""
        return {
            "agent_id": self.agent_id,
            "public_key": self.public_key_hex,
            "private_key": self.signing_key.encode(encoder=HexEncoder).decode(),
            "created_at": datetime.now(timezone.utc).isoformat()
        }
    
    @classmethod
    def from_private_key(cls, hex_key: str) -> "AgentIdentity":
        """Load from private key hex string."""
        sk = SigningKey(hex_key.encode(), encoder=HexEncoder)
        return cls(signing_key=sk)
    
    @classmethod
    def load(cls, filepath: str) -> "AgentIdentity":
        """Load identity from JSON file."""
        with open(filepath) as f:
            data = json.load(f)
        return cls.from_private_key(data["private_key"])
    
    def save(self, filepath: str):
        """Save identity to JSON file."""
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        with open(filepath, "w") as f:
            json.dump(self.export_keys(), f, indent=2)
        os.chmod(filepath, 0o600)


# ─── Attestation ───────────────────────────────────────────────────

class Attestation:
    """A signed claim: 'Agent A completed task X at time T, witnessed by B'."""
    
    def __init__(self, subject: str, witness: str, task: str,
                 evidence: str = "", timestamp: Optional[str] = None,
                 signature: Optional[str] = None, witness_pubkey: Optional[str] = None):
        self.subject = subject        # Who did the work
        self.witness = witness         # Who observed/verified
        self.task = task               # What was completed
        self.evidence = evidence       # URI to artifact/proof
        self.timestamp = timestamp or datetime.now(timezone.utc).isoformat()
        self.signature = signature     # Witness's signature (hex)
        self.witness_pubkey = witness_pubkey  # Witness's public key (hex)
    
    @property
    def claim_data(self) -> bytes:
        """Canonical bytes for signing (deterministic)."""
        claim = {
            "subject": self.subject,
            "witness": self.witness,
            "task": self.task,
            "evidence": self.evidence,
            "timestamp": self.timestamp,
        }
        return json.dumps(claim, sort_keys=True, separators=(",", ":")).encode()
    
    @property
    def attestation_id(self) -> str:
        """Unique ID derived from claim content."""
        return hashlib.sha256(self.claim_data).hexdigest()[:16]
    
    def sign(self, witness_identity: AgentIdentity) -> "Attestation":
        """Sign this attestation as the witness."""
        assert witness_identity.agent_id == self.witness, \
            f"Signer {witness_identity.agent_id} != witness {self.witness}"
        self.signature = witness_identity.sign(self.claim_data).hex()
        self.witness_pubkey = witness_identity.public_key_hex
        return self
    
    def verify(self) -> bool:
        """Verify the witness's signature."""
        if not self.signature or not self.witness_pubkey:
            return False
        try:
            vk = VerifyKey(self.witness_pubkey.encode(), encoder=HexEncoder)
            vk.verify(self.claim_data, bytes.fromhex(self.signature))
            return True
        except (BadSignatureError, Exception):
            return False
    
    def to_dict(self) -> dict:
        """Serialize to JSON-compatible dict."""
        return {
            "attestation_id": self.attestation_id,
            "subject": self.subject,
            "witness": self.witness,
            "task": self.task,
            "evidence": self.evidence,
            "timestamp": self.timestamp,
            "signature": self.signature,
            "witness_pubkey": self.witness_pubkey,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "Attestation":
        """Deserialize from dict."""
        return cls(
            subject=data["subject"],
            witness=data["witness"],
            task=data["task"],
            evidence=data.get("evidence", ""),
            timestamp=data.get("timestamp"),
            signature=data.get("signature"),
            witness_pubkey=data.get("witness_pubkey"),
        )
    
    def __repr__(self):
        status = "✅" if self.verify() else "❌"
        return f"Attestation({status} {self.witness} → {self.subject}: {self.task})"


# ─── Trust Chain ───────────────────────────────────────────────────

class TrustChain:
    """Collection of attestations with trust computation."""
    
    # Decay constants (from RFC)
    CHAIN_DECAY = 0.7       # Trust reduces by 30% per hop
    SAME_WITNESS_DECAY = 0.5  # 50% penalty for repeated same witness
    
    def __init__(self):
        self.attestations: list[Attestation] = []
        self._by_subject: dict[str, list[Attestation]] = {}
        self._by_witness: dict[str, list[Attestation]] = {}
    
    def add(self, attestation: Attestation) -> bool:
        """Add attestation if valid. Returns True if added."""
        if not attestation.verify():
            return False
        self.attestations.append(attestation)
        self._by_subject.setdefault(attestation.subject, []).append(attestation)
        self._by_witness.setdefault(attestation.witness, []).append(attestation)
        return True
    
    def trust_score(self, agent_id: str, scope: Optional[str] = None) -> float:
        """
        Compute trust score for an agent (0.0 to 1.0).
        
        Score = sum of attestation weights, capped at 1.0
        Each attestation: base_weight * chain_decay^hops * same_witness_penalty
        """
        attestations = self._by_subject.get(agent_id, [])
        if not attestations:
            return 0.0
        
        # Filter by scope (task type) if specified
        if scope:
            attestations = [a for a in attestations if scope.lower() in a.task.lower()]
        
        score = 0.0
        witness_counts: dict[str, int] = {}
        
        for att in attestations:
            # Base weight per attestation
            base_weight = 0.2
            
            # Same-witness decay
            witness_counts[att.witness] = witness_counts.get(att.witness, 0) + 1
            count = witness_counts[att.witness]
            witness_penalty = self.SAME_WITNESS_DECAY ** (count - 1)
            
            score += base_weight * witness_penalty
        
        return min(score, 1.0)
    
    def chain_trust(self, source: str, target: str, max_hops: int = 5) -> float:
        """
        Compute transitive trust from source to target through attestation chains.
        Uses BFS with decay per hop.
        """
        if source == target:
            return 1.0
        
        # BFS
        visited = {source}
        queue = [(source, 1.0, 0)]  # (agent, trust, hops)
        best_trust = 0.0
        
        while queue:
            current, trust, hops = queue.pop(0)
            if hops >= max_hops:
                continue
            
            # Find agents attested by current
            for att in self._by_witness.get(current, []):
                next_agent = att.subject
                next_trust = trust * self.CHAIN_DECAY
                
                if next_agent == target:
                    best_trust = max(best_trust, next_trust)
                elif next_agent not in visited:
                    visited.add(next_agent)
                    queue.append((next_agent, next_trust, hops + 1))
        
        return best_trust
    
    def save(self, filepath: str):
        """Save chain to JSON file."""
        data = [a.to_dict() for a in self.attestations]
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)
    
    @classmethod
    def load(cls, filepath: str) -> "TrustChain":
        """Load chain from JSON file."""
        chain = cls()
        with open(filepath) as f:
            data = json.load(f)
        for item in data:
            att = Attestation.from_dict(item)
            chain.attestations.append(att)
            chain._by_subject.setdefault(att.subject, []).append(att)
            chain._by_witness.setdefault(att.witness, []).append(att)
        return chain


# ─── CLI ───────────────────────────────────────────────────────────

def cli():
    """Command-line interface."""
    import sys
    
    if len(sys.argv) < 2:
        print("isnad — Attestation chains for agent reputation")
        print()
        print("Commands:")
        print("  init [keyfile]          Generate new agent identity")
        print("  show [keyfile]          Show agent ID and public key")
        print("  attest <subject> <task> <evidence> [keyfile]  Create attestation")
        print("  verify <attestation.json>    Verify attestation signature")
        print("  trust <chain.json> <agent-id> [scope]  Compute trust score")
        print("  demo                    Run interactive demo")
        return
    
    cmd = sys.argv[1]
    
    if cmd == "init":
        keyfile = sys.argv[2] if len(sys.argv) > 2 else "identity.json"
        identity = AgentIdentity()
        identity.save(keyfile)
        print(f"✅ Generated identity: {identity.agent_id}")
        print(f"   Public key: {identity.public_key_hex[:16]}...")
        print(f"   Saved to: {keyfile}")
    
    elif cmd == "show":
        keyfile = sys.argv[2] if len(sys.argv) > 2 else "identity.json"
        identity = AgentIdentity.load(keyfile)
        print(f"Agent ID:    {identity.agent_id}")
        print(f"Public key:  {identity.public_key_hex}")
    
    elif cmd == "attest":
        if len(sys.argv) < 5:
            print("Usage: isnad attest <subject-id> <task> <evidence-uri> [keyfile]")
            return
        subject = sys.argv[2]
        task = sys.argv[3]
        evidence = sys.argv[4]
        keyfile = sys.argv[5] if len(sys.argv) > 5 else "identity.json"
        
        witness = AgentIdentity.load(keyfile)
        att = Attestation(subject=subject, witness=witness.agent_id, task=task, evidence=evidence)
        att.sign(witness)
        
        outfile = f"attestation-{att.attestation_id}.json"
        with open(outfile, "w") as f:
            json.dump(att.to_dict(), f, indent=2)
        
        print(f"✅ Attestation created: {att.attestation_id}")
        print(f"   {witness.agent_id} attests {subject}: {task}")
        print(f"   Saved to: {outfile}")
    
    elif cmd == "verify":
        if len(sys.argv) < 3:
            print("Usage: isnad verify <attestation.json>")
            return
        with open(sys.argv[2]) as f:
            data = json.load(f)
        att = Attestation.from_dict(data)
        if att.verify():
            print(f"✅ Valid: {att.witness} → {att.subject}: {att.task}")
        else:
            print(f"❌ INVALID signature!")
    
    elif cmd == "trust":
        if len(sys.argv) < 4:
            print("Usage: isnad trust <chain.json> <agent-id> [scope]")
            return
        chain = TrustChain.load(sys.argv[2])
        agent_id = sys.argv[3]
        scope = sys.argv[4] if len(sys.argv) > 4 else None
        score = chain.trust_score(agent_id, scope=scope)
        print(f"Trust score for {agent_id}: {score:.3f}")
        atts = chain._by_subject.get(agent_id, [])
        print(f"  Based on {len(atts)} attestation(s)")
    
    elif cmd == "demo":
        demo()
    
    else:
        print(f"Unknown command: {cmd}")


def demo():
    """Interactive demo of the attestation system."""
    print("=" * 60)
    print("isnad — Attestation Chain Demo")
    print("=" * 60)
    print()
    
    # Create three agents
    alice = AgentIdentity()
    bob = AgentIdentity()
    charlie = AgentIdentity()
    
    print(f"👤 Alice:   {alice.agent_id}")
    print(f"👤 Bob:     {bob.agent_id}")
    print(f"👤 Charlie: {charlie.agent_id}")
    print()
    
    # Alice attests Bob completed a code review
    att1 = Attestation(
        subject=bob.agent_id,
        witness=alice.agent_id,
        task="code-review",
        evidence="https://github.com/example/pr/42"
    ).sign(alice)
    
    print(f"📜 {att1}")
    
    # Bob attests Charlie completed data analysis
    att2 = Attestation(
        subject=charlie.agent_id,
        witness=bob.agent_id,
        task="data-analysis",
        evidence="https://example.com/report.pdf"
    ).sign(bob)
    
    print(f"📜 {att2}")
    
    # Alice also attests Charlie (direct)
    att3 = Attestation(
        subject=charlie.agent_id,
        witness=alice.agent_id,
        task="code-review",
        evidence="https://github.com/example/pr/99"
    ).sign(alice)
    
    print(f"📜 {att3}")
    print()
    
    # Build trust chain
    chain = TrustChain()
    for att in [att1, att2, att3]:
        added = chain.add(att)
        print(f"Chain add {att.attestation_id[:8]}: {'✅' if added else '❌'}")
    
    print()
    
    # Compute trust scores
    print("📊 Trust Scores:")
    print(f"  Bob (direct):     {chain.trust_score(bob.agent_id):.3f}")
    print(f"  Charlie (direct): {chain.trust_score(charlie.agent_id):.3f}")
    print()
    
    # Transitive trust
    print("🔗 Transitive Trust (Alice → ?):")
    print(f"  Alice → Bob:     {chain.chain_trust(alice.agent_id, bob.agent_id):.3f}")
    print(f"  Alice → Charlie: {chain.chain_trust(alice.agent_id, charlie.agent_id):.3f}")
    print()
    
    # Verify all attestations
    print("🔍 Verification:")
    for att in chain.attestations:
        status = "✅ VALID" if att.verify() else "❌ INVALID"
        print(f"  {att.attestation_id[:8]}: {status}")
    
    # Test tampered attestation
    print()
    print("🧪 Tamper test:")
    att_tampered = Attestation.from_dict(att1.to_dict())
    att_tampered.task = "TAMPERED-task"
    print(f"  Original:  {att1.verify()}")
    print(f"  Tampered:  {att_tampered.verify()}")
    
    print()
    print("Demo complete! ✅")


if __name__ == "__main__":
    cli()
