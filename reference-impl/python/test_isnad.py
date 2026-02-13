#!/usr/bin/env python3
"""Tests for isnad reference implementation."""

import json
import os
import tempfile
from isnad import AgentIdentity, Attestation, TrustChain


def test_identity_generation():
    """Test keypair generation and consistency."""
    agent = AgentIdentity()
    assert agent.agent_id.startswith("agent:")
    assert len(agent.public_key_hex) == 64  # 32 bytes hex
    # Same key → same agent ID
    agent2 = AgentIdentity.from_private_key(
        agent.signing_key.encode(encoder=__import__('nacl.encoding', fromlist=['HexEncoder']).HexEncoder).decode()
    )
    assert agent.agent_id == agent2.agent_id
    print("✅ test_identity_generation")


def test_identity_save_load():
    """Test identity persistence."""
    agent = AgentIdentity()
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name
    try:
        agent.save(path)
        loaded = AgentIdentity.load(path)
        assert agent.agent_id == loaded.agent_id
        assert agent.public_key_hex == loaded.public_key_hex
    finally:
        os.unlink(path)
    print("✅ test_identity_save_load")


def test_attestation_sign_verify():
    """Test attestation creation and signature verification."""
    witness = AgentIdentity()
    subject = AgentIdentity()
    
    att = Attestation(
        subject=subject.agent_id,
        witness=witness.agent_id,
        task="code-review",
        evidence="https://github.com/example/pr/1"
    ).sign(witness)
    
    assert att.verify() is True
    assert att.signature is not None
    assert att.witness_pubkey is not None
    print("✅ test_attestation_sign_verify")


def test_attestation_tamper_detection():
    """Test that tampered attestations fail verification."""
    witness = AgentIdentity()
    subject = AgentIdentity()
    
    att = Attestation(
        subject=subject.agent_id,
        witness=witness.agent_id,
        task="data-analysis",
        evidence="https://example.com/report"
    ).sign(witness)
    
    assert att.verify() is True
    
    # Tamper with task
    tampered = Attestation.from_dict(att.to_dict())
    tampered.task = "EVIL-task"
    assert tampered.verify() is False
    
    # Tamper with subject
    tampered2 = Attestation.from_dict(att.to_dict())
    tampered2.subject = "agent:evil"
    assert tampered2.verify() is False
    
    # Tamper with timestamp
    tampered3 = Attestation.from_dict(att.to_dict())
    tampered3.timestamp = "2020-01-01T00:00:00Z"
    assert tampered3.verify() is False
    
    print("✅ test_attestation_tamper_detection")


def test_attestation_wrong_signer():
    """Test that signing with wrong identity fails."""
    witness = AgentIdentity()
    imposter = AgentIdentity()
    subject = AgentIdentity()
    
    att = Attestation(
        subject=subject.agent_id,
        witness=witness.agent_id,
        task="test"
    )
    
    try:
        att.sign(imposter)  # Wrong identity
        assert False, "Should have raised AssertionError"
    except AssertionError:
        pass
    
    print("✅ test_attestation_wrong_signer")


def test_attestation_serialization():
    """Test JSON round-trip."""
    witness = AgentIdentity()
    subject = AgentIdentity()
    
    att = Attestation(
        subject=subject.agent_id,
        witness=witness.agent_id,
        task="research",
        evidence="https://example.com"
    ).sign(witness)
    
    data = att.to_dict()
    restored = Attestation.from_dict(data)
    
    assert restored.verify() is True
    assert restored.subject == att.subject
    assert restored.witness == att.witness
    assert restored.task == att.task
    assert restored.attestation_id == att.attestation_id
    print("✅ test_attestation_serialization")


def test_trust_chain_basic():
    """Test basic trust chain operations."""
    chain = TrustChain()
    alice = AgentIdentity()
    bob = AgentIdentity()
    
    att = Attestation(
        subject=bob.agent_id,
        witness=alice.agent_id,
        task="code-review",
        evidence="https://example.com"
    ).sign(alice)
    
    assert chain.add(att) is True
    assert chain.trust_score(bob.agent_id) == 0.2
    assert chain.trust_score(alice.agent_id) == 0.0  # No attestations FOR alice
    print("✅ test_trust_chain_basic")


def test_trust_chain_rejects_invalid():
    """Test that invalid attestations are rejected."""
    chain = TrustChain()
    
    # Unsigned attestation
    att = Attestation(
        subject="agent:fake",
        witness="agent:faker",
        task="test"
    )
    assert chain.add(att) is False
    assert len(chain.attestations) == 0
    print("✅ test_trust_chain_rejects_invalid")


def test_same_witness_decay():
    """Test diminishing returns for same witness."""
    chain = TrustChain()
    alice = AgentIdentity()
    bob = AgentIdentity()
    
    # Alice attests Bob 3 times
    for i in range(3):
        att = Attestation(
            subject=bob.agent_id,
            witness=alice.agent_id,
            task=f"task-{i}",
            evidence=f"https://example.com/{i}"
        ).sign(alice)
        chain.add(att)
    
    score = chain.trust_score(bob.agent_id)
    # 0.2 * 1.0 + 0.2 * 0.5 + 0.2 * 0.25 = 0.2 + 0.1 + 0.05 = 0.35
    assert abs(score - 0.35) < 0.001
    print("✅ test_same_witness_decay")


def test_multiple_witnesses():
    """Test that different witnesses contribute independently."""
    chain = TrustChain()
    witnesses = [AgentIdentity() for _ in range(5)]
    subject = AgentIdentity()
    
    for w in witnesses:
        att = Attestation(
            subject=subject.agent_id,
            witness=w.agent_id,
            task="verify",
            evidence="https://example.com"
        ).sign(w)
        chain.add(att)
    
    score = chain.trust_score(subject.agent_id)
    # 5 * 0.2 = 1.0 (capped)
    assert score == 1.0
    print("✅ test_multiple_witnesses")


def test_transitive_trust():
    """Test trust propagation through chains."""
    chain = TrustChain()
    alice = AgentIdentity()
    bob = AgentIdentity()
    charlie = AgentIdentity()
    
    # Alice → Bob
    att1 = Attestation(
        subject=bob.agent_id,
        witness=alice.agent_id,
        task="trusted",
        evidence="https://example.com"
    ).sign(alice)
    chain.add(att1)
    
    # Bob → Charlie
    att2 = Attestation(
        subject=charlie.agent_id,
        witness=bob.agent_id,
        task="trusted",
        evidence="https://example.com"
    ).sign(bob)
    chain.add(att2)
    
    # Direct: Alice → Bob = 0.7 (chain_decay)
    direct = chain.chain_trust(alice.agent_id, bob.agent_id)
    assert abs(direct - 0.7) < 0.001
    
    # Transitive: Alice → Charlie = 0.7 * 0.7 = 0.49
    transitive = chain.chain_trust(alice.agent_id, charlie.agent_id)
    assert abs(transitive - 0.49) < 0.001
    
    print("✅ test_transitive_trust")


def test_scope_filtering():
    """Test trust score filtering by task scope."""
    chain = TrustChain()
    alice = AgentIdentity()
    bob = AgentIdentity()
    
    # Bob has attestations for code and research
    att1 = Attestation(subject=bob.agent_id, witness=alice.agent_id,
                       task="code-review", evidence="").sign(alice)
    att2 = Attestation(subject=bob.agent_id, witness=alice.agent_id,
                       task="research-analysis", evidence="").sign(alice)
    chain.add(att1)
    chain.add(att2)
    
    # Scoped scores
    code_score = chain.trust_score(bob.agent_id, scope="code")
    research_score = chain.trust_score(bob.agent_id, scope="research")
    total_score = chain.trust_score(bob.agent_id)
    
    assert code_score < total_score
    assert research_score < total_score
    print("✅ test_scope_filtering")


def test_chain_save_load():
    """Test chain persistence."""
    chain = TrustChain()
    alice = AgentIdentity()
    bob = AgentIdentity()
    
    att = Attestation(subject=bob.agent_id, witness=alice.agent_id,
                      task="test", evidence="").sign(alice)
    chain.add(att)
    
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name
    try:
        chain.save(path)
        loaded = TrustChain.load(path)
        assert len(loaded.attestations) == 1
        assert loaded.trust_score(bob.agent_id) == chain.trust_score(bob.agent_id)
    finally:
        os.unlink(path)
    print("✅ test_chain_save_load")


if __name__ == "__main__":
    tests = [
        test_identity_generation,
        test_identity_save_load,
        test_attestation_sign_verify,
        test_attestation_tamper_detection,
        test_attestation_wrong_signer,
        test_attestation_serialization,
        test_trust_chain_basic,
        test_trust_chain_rejects_invalid,
        test_same_witness_decay,
        test_multiple_witnesses,
        test_transitive_trust,
        test_scope_filtering,
        test_chain_save_load,
    ]
    
    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"❌ {test.__name__}: {e}")
            failed += 1
    
    print(f"\n{'='*40}")
    print(f"Results: {passed} passed, {failed} failed, {passed+failed} total")
