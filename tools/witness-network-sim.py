#!/usr/bin/env python3
"""witness-network-sim.py — Simulates witness network consistency guarantees.

Models the ArmoredWitness / OmniWitness pattern for agent transparency logs.
Answers: how many witnesses needed for split-view detection at given adversary strength?

Based on:
- transparency-dev/witness (OmniWitness, ArmoredWitness)
- C2SP tlog-witness spec
- Gossip protocol (arxiv 2011.04551)

Key insight: witnesses don't validate contents — just append-only consistency.
Cost is O(log n) per verification. The question is quorum size vs collusion budget.
"""

import argparse
import json
import random
import hashlib
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Checkpoint:
    """A signed commitment to log state at a given size."""
    log_id: str
    size: int
    root_hash: str
    signatures: list = field(default_factory=list)

    def sign(self, witness_id: str):
        sig = hashlib.sha256(f"{witness_id}:{self.log_id}:{self.size}:{self.root_hash}".encode()).hexdigest()[:16]
        self.signatures.append({"witness": witness_id, "sig": sig})


@dataclass
class Witness:
    """A witness that tracks log consistency."""
    witness_id: str
    compromised: bool = False
    last_checkpoint: Optional[dict] = None  # {log_id: Checkpoint}

    def __post_init__(self):
        if self.last_checkpoint is None:
            self.last_checkpoint = {}

    def verify_and_sign(self, checkpoint: Checkpoint, is_split_view: bool = False) -> bool:
        """Verify consistency and countersign. Returns True if signed."""
        log_id = checkpoint.log_id

        if self.compromised and is_split_view:
            # Compromised witness signs split views
            checkpoint.sign(self.witness_id)
            self.last_checkpoint[log_id] = checkpoint
            return True

        if log_id not in self.last_checkpoint:
            # TOFU — trust on first use
            checkpoint.sign(self.witness_id)
            self.last_checkpoint[log_id] = checkpoint
            return True

        prev = self.last_checkpoint[log_id]

        if is_split_view:
            # Honest witness detects split view — refuses to sign
            return False

        # Consistent evolution — sign it
        if checkpoint.size >= prev.size:
            checkpoint.sign(self.witness_id)
            self.last_checkpoint[log_id] = checkpoint
            return True

        return False


def simulate_split_view(
    n_witnesses: int,
    n_compromised: int,
    quorum_size: int,
    n_rounds: int = 1000,
) -> dict:
    """Simulate split-view attack detection rate.

    A split view succeeds if the adversary can get quorum_size signatures
    on BOTH the honest checkpoint AND the forked checkpoint.
    """
    detections = 0
    successful_splits = 0
    failed_splits = 0

    for _ in range(n_rounds):
        # Create witnesses
        witnesses = []
        compromised_ids = set(random.sample(range(n_witnesses), min(n_compromised, n_witnesses)))
        for i in range(n_witnesses):
            witnesses.append(Witness(
                witness_id=f"witness-{i}",
                compromised=(i in compromised_ids),
            ))

        # Phase 1: honest checkpoint (all witnesses see it)
        honest_cp = Checkpoint(log_id="agent-log-1", size=100, root_hash="aaa111")
        for w in witnesses:
            w.verify_and_sign(honest_cp, is_split_view=False)

        # Phase 2: adversary tries split view
        fork_cp = Checkpoint(log_id="agent-log-1", size=100, root_hash="bbb222")
        for w in witnesses:
            w.verify_and_sign(fork_cp, is_split_view=True)

        fork_sigs = len(fork_cp.signatures)

        if fork_sigs >= quorum_size:
            successful_splits += 1
        else:
            detections += 1
            failed_splits += 1

    detection_rate = detections / n_rounds
    return {
        "n_witnesses": n_witnesses,
        "n_compromised": n_compromised,
        "quorum_size": quorum_size,
        "n_rounds": n_rounds,
        "detection_rate": round(detection_rate, 4),
        "successful_splits": successful_splits,
        "failed_splits": failed_splits,
        "grade": grade_network(detection_rate),
    }


def grade_network(detection_rate: float) -> str:
    if detection_rate >= 0.999:
        return "A"
    elif detection_rate >= 0.99:
        return "B"
    elif detection_rate >= 0.95:
        return "C"
    elif detection_rate >= 0.90:
        return "D"
    else:
        return "F"


def sweep(max_witnesses: int = 20, max_compromised_frac: float = 0.5, n_rounds: int = 1000) -> list:
    """Sweep parameter space: witnesses × compromised fraction × quorum strategies."""
    results = []
    for n in [3, 5, 7, 10, 15, max_witnesses]:
        if n > max_witnesses:
            continue
        for comp_frac in [0.1, 0.2, 0.33, max_compromised_frac]:
            n_comp = max(1, int(n * comp_frac))
            for quorum_name, quorum_fn in [
                ("majority", lambda x: x // 2 + 1),
                ("supermajority", lambda x: (2 * x) // 3 + 1),
                ("all", lambda x: x),
            ]:
                q = quorum_fn(n)
                result = simulate_split_view(n, n_comp, q, n_rounds)
                result["quorum_strategy"] = quorum_name
                results.append(result)
    return results


def main():
    parser = argparse.ArgumentParser(description="Witness network split-view detection simulator")
    parser.add_argument("--witnesses", "-w", type=int, default=7, help="Number of witnesses")
    parser.add_argument("--compromised", "-c", type=int, default=2, help="Number of compromised witnesses")
    parser.add_argument("--quorum", "-q", type=int, default=None, help="Quorum size (default: majority)")
    parser.add_argument("--rounds", "-r", type=int, default=1000, help="Simulation rounds")
    parser.add_argument("--sweep", action="store_true", help="Run parameter sweep")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    if args.sweep:
        results = sweep(n_rounds=args.rounds)
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            print(f"{'W':>3} {'Comp':>4} {'Quorum':>14} {'Q':>3} {'Detect':>8} {'Grade':>5}")
            print("-" * 42)
            for r in results:
                print(f"{r['n_witnesses']:>3} {r['n_compromised']:>4} {r['quorum_strategy']:>14} {r['quorum_size']:>3} {r['detection_rate']:>8.4f} {r['grade']:>5}")
        return

    quorum = args.quorum or (args.witnesses // 2 + 1)
    result = simulate_split_view(args.witnesses, args.compromised, quorum, args.rounds)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Witness Network Split-View Simulation")
        print(f"=" * 40)
        print(f"Witnesses:    {result['n_witnesses']}")
        print(f"Compromised:  {result['n_compromised']}")
        print(f"Quorum:       {result['quorum_size']}")
        print(f"Rounds:       {result['n_rounds']}")
        print(f"Detection:    {result['detection_rate']:.2%}")
        print(f"Grade:        {result['grade']}")
        print()
        if result['successful_splits'] > 0:
            print(f"⚠️  {result['successful_splits']} successful split-view attacks in {result['n_rounds']} rounds")
        else:
            print(f"✅ No successful split-view attacks")


if __name__ == "__main__":
    main()
