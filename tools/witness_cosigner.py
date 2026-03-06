#!/usr/bin/env python3
"""witness_cosigner.py — CoSi-inspired witness cosigning simulator for agent attestations.

Based on Syta et al. "Keeping Authorities Honest or Bust" (IEEE S&P 2016).
Simulates scalable Schnorr multisignature aggregation over spanning trees.

Key insight: VSS breaks at ~32 nodes, naive sigs at ~256. Tree-based
aggregation scales to thousands. Agent attestation needs this.

Usage:
    python witness_cosigner.py --witnesses 100 --threshold 67 --depth 3
    python witness_cosigner.py --demo
"""

import argparse
import hashlib
import json
import math
import random
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Witness:
    """A witness node in the cosigning tree."""
    id: int
    public_key: str  # Simulated as hex string
    secret: int = 0  # Simulated secret key
    commit: int = 0  # v_i
    response: int = 0  # r_i
    available: bool = True
    validated: bool = False
    latency_ms: float = 0.0  # Simulated network latency


@dataclass
class TreeNode:
    """Node in the spanning tree."""
    witness: Witness
    children: list = field(default_factory=list)
    aggregate_commit: int = 0
    aggregate_response: int = 0
    missing_witnesses: list = field(default_factory=list)


@dataclass
class CollectiveSignature:
    """Result of a CoSi signing round."""
    challenge: str
    aggregate_response: int
    present_witnesses: list
    missing_witnesses: list
    total_witnesses: int
    signing_latency_ms: float
    signature_size_bytes: int
    tree_depth: int
    branching_factor: int
    

def generate_witnesses(n: int, failure_rate: float = 0.02) -> list[Witness]:
    """Generate n witnesses with simulated keys and random availability."""
    witnesses = []
    for i in range(n):
        w = Witness(
            id=i,
            public_key=hashlib.sha256(f"witness-{i}".encode()).hexdigest()[:16],
            secret=random.randint(1, 2**32),
            available=random.random() > failure_rate,
            latency_ms=random.uniform(10, 200)  # Global distribution
        )
        witnesses.append(w)
    return witnesses


def build_spanning_tree(witnesses: list[Witness], branching_factor: int) -> TreeNode:
    """Build a B-ary spanning tree from witness list. Leader is witness[0]."""
    nodes = [TreeNode(witness=w) for w in witnesses]
    
    # BFS tree construction
    queue = [0]
    next_child = 1
    while queue and next_child < len(nodes):
        parent_idx = queue.pop(0)
        for _ in range(branching_factor):
            if next_child >= len(nodes):
                break
            nodes[parent_idx].children.append(nodes[next_child])
            queue.append(next_child)
            next_child += 1
    
    return nodes[0]


def tree_depth(node: TreeNode) -> int:
    """Calculate tree depth."""
    if not node.children:
        return 0
    return 1 + max(tree_depth(c) for c in node.children)


def commitment_phase(node: TreeNode) -> tuple[int, list[int], float]:
    """Phase 2: Bottom-up commit aggregation. Returns (aggregate_commit, missing, max_latency)."""
    if not node.witness.available:
        return 0, [node.witness.id], 0
    
    # Generate individual commit
    node.witness.commit = random.randint(1, 2**64)
    aggregate = node.witness.commit
    missing = []
    max_latency = node.witness.latency_ms
    
    for child in node.children:
        child_agg, child_missing, child_lat = commitment_phase(child)
        if child_agg > 0:
            aggregate ^= child_agg  # Simulated group operation
        missing.extend(child_missing)
        max_latency = max(max_latency, child_lat + node.witness.latency_ms)
    
    node.aggregate_commit = aggregate
    node.missing_witnesses = missing
    return aggregate, missing, max_latency


def challenge_phase(aggregate_commit: int, statement: str) -> str:
    """Phase 3: Compute collective challenge c = H(V_hat || S)."""
    h = hashlib.sha256()
    h.update(aggregate_commit.to_bytes(8, 'big'))
    h.update(statement.encode())
    return h.hexdigest()


def response_phase(node: TreeNode, challenge: str) -> tuple[int, float]:
    """Phase 4: Bottom-up response aggregation."""
    if not node.witness.available:
        return 0, 0
    
    # Individual response: r_i = v_i - c*x_i (simulated)
    c_int = int(challenge[:8], 16)
    node.witness.response = node.witness.commit ^ (c_int * node.witness.secret % (2**64))
    aggregate = node.witness.response
    max_latency = node.witness.latency_ms
    
    for child in node.children:
        child_resp, child_lat = response_phase(child, challenge)
        aggregate ^= child_resp
        max_latency = max(max_latency, child_lat + node.witness.latency_ms)
    
    node.aggregate_response = aggregate
    return aggregate, max_latency


def cosign(witnesses: list[Witness], statement: str, 
           branching_factor: int = 32, threshold: float = 0.67) -> CollectiveSignature:
    """Execute a full CoSi signing round."""
    
    # Phase 1: Build tree + announce
    tree = build_spanning_tree(witnesses, branching_factor)
    depth = tree_depth(tree)
    
    # Phase 2: Commitment
    agg_commit, missing, commit_latency = commitment_phase(tree)
    
    # Phase 3: Challenge
    challenge = challenge_phase(agg_commit, statement)
    
    # Phase 4: Response
    agg_response, response_latency = response_phase(tree, challenge)
    
    total_latency = commit_latency + response_latency  # Two round-trips
    
    present = [w.id for w in witnesses if w.available]
    
    # Signature size: ~100 bytes base (challenge + response) + exception encoding
    n_missing = len(missing)
    if n_missing == 0:
        sig_size = 96  # Just (c, r) on Ed25519
    elif n_missing < len(witnesses) // 2:
        sig_size = 96 + n_missing * 4  # List missing witnesses
    else:
        sig_size = 96 + len(present) * 4  # List present witnesses
    
    return CollectiveSignature(
        challenge=challenge,
        aggregate_response=agg_response,
        present_witnesses=present,
        missing_witnesses=missing,
        total_witnesses=len(witnesses),
        signing_latency_ms=total_latency,
        signature_size_bytes=sig_size,
        tree_depth=depth,
        branching_factor=branching_factor,
    )


def verify_threshold(sig: CollectiveSignature, threshold: float) -> dict:
    """Verify that signature meets threshold requirements."""
    present_ratio = len(sig.present_witnesses) / sig.total_witnesses
    meets_threshold = present_ratio >= threshold
    
    return {
        "meets_threshold": meets_threshold,
        "present_ratio": round(present_ratio, 3),
        "threshold": threshold,
        "present": len(sig.present_witnesses),
        "missing": len(sig.missing_witnesses),
        "total": sig.total_witnesses,
        "signature_size_bytes": sig.signature_size_bytes,
        "latency_ms": round(sig.signing_latency_ms, 1),
        "tree_depth": sig.tree_depth,
    }


def compare_approaches(n_witnesses: int) -> dict:
    """Compare CoSi vs naive vs JVSS scaling."""
    results = {}
    
    # CoSi: O(log N) per node, O(N) total
    cosi_latency = 200 * 2 * math.ceil(math.log(n_witnesses, 32))  # 2 round-trips, depth log_32(N)
    cosi_sig_size = 96  # Constant
    cosi_compute_per_node = 0.1  # ms, constant
    
    # Naive: O(N) at leader
    naive_latency = 200 + n_witnesses * 0.5  # One round, but N signatures to collect
    naive_sig_size = n_witnesses * 64  # N individual signatures
    naive_compute_per_node = n_witnesses * 0.3  # Verify all at leader
    
    # JVSS: O(N^2) dealing
    jvss_latency = n_witnesses * n_witnesses * 0.01 + 200 * 3
    jvss_sig_size = 96  # Threshold sig is compact
    jvss_compute_per_node = n_witnesses * n_witnesses * 0.05
    
    results["cosi"] = {
        "latency_ms": round(cosi_latency),
        "sig_bytes": cosi_sig_size,
        "compute_ms": round(cosi_compute_per_node, 1),
        "scalable": n_witnesses <= 33000,
    }
    results["naive"] = {
        "latency_ms": round(naive_latency),
        "sig_bytes": naive_sig_size,
        "compute_ms": round(naive_compute_per_node, 1),
        "scalable": n_witnesses <= 256,
    }
    results["jvss"] = {
        "latency_ms": round(jvss_latency),
        "sig_bytes": jvss_sig_size,
        "compute_ms": round(jvss_compute_per_node, 1),
        "scalable": n_witnesses <= 32,
    }
    
    return results


def grade_cosigning(sig: CollectiveSignature, threshold: float = 0.67) -> str:
    """Grade a cosigning result A-F."""
    present_ratio = len(sig.present_witnesses) / sig.total_witnesses
    
    if present_ratio >= 0.95 and sig.signing_latency_ms < 3000:
        return "A"
    elif present_ratio >= 0.85:
        return "B"
    elif present_ratio >= threshold:
        return "C"
    elif present_ratio >= 0.50:
        return "D"
    else:
        return "F"


def demo():
    """Run demonstration scenarios."""
    print("=" * 60)
    print("WITNESS COSIGNER — CoSi-Inspired Agent Attestation")
    print("Based on Syta et al. IEEE S&P 2016")
    print("=" * 60)
    
    # Scenario 1: Small group
    print("\n📋 Scenario 1: 10 witnesses (small group)")
    witnesses = generate_witnesses(10, failure_rate=0.0)
    sig = cosign(witnesses, "scope: read-only access to /api/data", branching_factor=4)
    result = verify_threshold(sig, 0.67)
    grade = grade_cosigning(sig)
    print(f"   Grade: {grade} | Present: {result['present']}/{result['total']} | "
          f"Latency: {result['latency_ms']}ms | Sig: {result['signature_size_bytes']}B")
    
    # Scenario 2: Medium group with failures
    print("\n📋 Scenario 2: 100 witnesses (2% failure rate)")
    witnesses = generate_witnesses(100, failure_rate=0.02)
    sig = cosign(witnesses, "scope: heartbeat monitor, 20min TTL", branching_factor=16)
    result = verify_threshold(sig, 0.67)
    grade = grade_cosigning(sig)
    print(f"   Grade: {grade} | Present: {result['present']}/{result['total']} | "
          f"Latency: {result['latency_ms']}ms | Sig: {result['signature_size_bytes']}B")
    
    # Scenario 3: Large scale
    print("\n📋 Scenario 3: 8000 witnesses (CoSi paper scale)")
    witnesses = generate_witnesses(8000, failure_rate=0.01)
    sig = cosign(witnesses, "scope: NIST submission, merge tools branch", branching_factor=32)
    result = verify_threshold(sig, 0.67)
    grade = grade_cosigning(sig)
    print(f"   Grade: {grade} | Present: {result['present']}/{result['total']} | "
          f"Latency: {result['latency_ms']}ms | Sig: {result['signature_size_bytes']}B | "
          f"Depth: {result['tree_depth']}")
    
    # Comparison
    print("\n📊 Scaling Comparison (N=1000 witnesses):")
    comp = compare_approaches(1000)
    for approach, metrics in comp.items():
        status = "✅" if metrics["scalable"] else "❌"
        print(f"   {status} {approach:6s}: latency={metrics['latency_ms']:>8}ms  "
              f"sig={metrics['sig_bytes']:>6}B  compute={metrics['compute_ms']:>8.1f}ms/node")
    
    print("\n📊 Scaling Comparison (N=100 witnesses):")
    comp = compare_approaches(100)
    for approach, metrics in comp.items():
        status = "✅" if metrics["scalable"] else "❌"
        print(f"   {status} {approach:6s}: latency={metrics['latency_ms']:>8}ms  "
              f"sig={metrics['sig_bytes']:>6}B  compute={metrics['compute_ms']:>8.1f}ms/node")
    
    # Agent attestation application
    print("\n🦊 Agent Attestation Application:")
    print("   Current isnad: 1-3 attesters (naive approach)")
    print("   With CoSi: scale to 1000+ diverse witnesses")
    print("   Key benefit: ~100B signatures regardless of witness count")
    print("   Geopolitical predicates: threshold per region, not just global")
    print("   MMD analog: scope-commit window = 5min (vs CT's 24hr)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CoSi-inspired witness cosigning")
    parser.add_argument("--witnesses", type=int, default=100)
    parser.add_argument("--threshold", type=float, default=0.67)
    parser.add_argument("--depth", type=int, default=3)
    parser.add_argument("--failure-rate", type=float, default=0.02)
    parser.add_argument("--branching-factor", type=int, default=32)
    parser.add_argument("--statement", default="scope: default agent action")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--compare", action="store_true")
    args = parser.parse_args()
    
    if args.demo:
        demo()
    elif args.compare:
        for n in [10, 32, 100, 256, 1000, 8000]:
            comp = compare_approaches(n)
            print(f"\nN={n}:")
            for approach, m in comp.items():
                s = "✅" if m["scalable"] else "❌"
                print(f"  {s} {approach}: {m['latency_ms']}ms, {m['sig_bytes']}B")
    else:
        witnesses = generate_witnesses(args.witnesses, args.failure_rate)
        sig = cosign(witnesses, args.statement, args.branching_factor, args.threshold)
        result = verify_threshold(sig, args.threshold)
        grade = grade_cosigning(sig, args.threshold)
        print(json.dumps({"grade": grade, **result}, indent=2))
