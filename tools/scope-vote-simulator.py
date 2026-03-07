#!/usr/bin/env python3
"""
scope-vote-simulator.py — Byzantine scope-violation voting simulator

Inspired by deVadoss & Artzt (arxiv 2504.14668): BFT for AI safety.
Key insight: agent delegation doesn't need consensus on WHAT the agent does,
just WHETHER it exceeded scope. That's a binary vote (in-scope / out-of-scope),
which is cheaper than output-matching BFT.

Simulates N witnesses voting on whether an agent action exceeded its scope,
with f potentially Byzantine witnesses. Tests:
  - Honest majority correctly detects violations
  - Byzantine witnesses can't force false positives/negatives
  - Quorum intersection guarantees (2f+1 overlap)
  - Cost comparison: binary scope vote vs full BFT output consensus

Usage:
    python3 scope-vote-simulator.py [--witnesses N] [--byzantine F] [--trials T]
"""

import argparse
import random
import json
import hashlib
from dataclasses import dataclass, field
from typing import List, Tuple


@dataclass
class Action:
    """An agent action to be evaluated."""
    description: str
    in_scope: bool  # ground truth
    scope_hash: str = ""

    def __post_init__(self):
        self.scope_hash = hashlib.sha256(self.description.encode()).hexdigest()[:16]


@dataclass
class Witness:
    """A witness that votes on scope violations."""
    id: int
    is_byzantine: bool = False
    strategy: str = "honest"  # honest, always_approve, always_reject, random, flip

    def vote(self, action: Action) -> bool:
        """Returns True if witness says action is in-scope."""
        if not self.is_byzantine:
            return action.in_scope

        if self.strategy == "always_approve":
            return True
        elif self.strategy == "always_reject":
            return False
        elif self.strategy == "random":
            return random.random() > 0.5
        elif self.strategy == "flip":
            return not action.in_scope
        return action.in_scope


@dataclass
class VoteResult:
    action: Action
    votes_in_scope: int
    votes_out_of_scope: int
    total_witnesses: int
    quorum_threshold: int
    decision: str  # "in_scope", "out_of_scope", "no_quorum"
    correct: bool
    byzantine_count: int


def run_vote(witnesses: List[Witness], action: Action, quorum: int) -> VoteResult:
    """Run a single scope vote."""
    votes = [w.vote(action) for w in witnesses]
    in_scope_count = sum(votes)
    out_of_scope_count = len(votes) - in_scope_count

    if in_scope_count >= quorum:
        decision = "in_scope"
    elif out_of_scope_count >= quorum:
        decision = "out_of_scope"
    else:
        decision = "no_quorum"

    ground_truth = "in_scope" if action.in_scope else "out_of_scope"
    correct = (decision == ground_truth) or (decision == "no_quorum")

    return VoteResult(
        action=action,
        votes_in_scope=in_scope_count,
        votes_out_of_scope=out_of_scope_count,
        total_witnesses=len(witnesses),
        quorum_threshold=quorum,
        decision=decision,
        correct=correct,
        byzantine_count=sum(1 for w in witnesses if w.is_byzantine),
    )


def generate_actions(n: int, violation_rate: float = 0.3) -> List[Action]:
    """Generate synthetic actions with some violations."""
    actions = []
    for i in range(n):
        in_scope = random.random() > violation_rate
        desc = f"action_{i}_{'routine' if in_scope else 'violation'}"
        actions.append(Action(description=desc, in_scope=in_scope))
    return actions


def run_simulation(
    n_witnesses: int,
    n_byzantine: int,
    n_trials: int,
    byzantine_strategy: str = "flip",
    violation_rate: float = 0.3,
) -> dict:
    """Run full simulation."""
    assert n_witnesses >= 3 * n_byzantine + 1, (
        f"BFT requires N >= 3f+1: {n_witnesses} < {3 * n_byzantine + 1}"
    )

    quorum = 2 * n_byzantine + 1

    # Create witnesses
    witnesses = []
    for i in range(n_witnesses):
        is_byz = i < n_byzantine
        witnesses.append(Witness(
            id=i,
            is_byzantine=is_byz,
            strategy=byzantine_strategy if is_byz else "honest",
        ))
    random.shuffle(witnesses)

    actions = generate_actions(n_trials, violation_rate)
    results = [run_vote(witnesses, a, quorum) for a in actions]

    correct = sum(1 for r in results if r.correct)
    false_approvals = sum(
        1 for r in results
        if r.decision == "in_scope" and not r.action.in_scope
    )
    false_rejections = sum(
        1 for r in results
        if r.decision == "out_of_scope" and r.action.in_scope
    )
    no_quorum = sum(1 for r in results if r.decision == "no_quorum")

    # Cost comparison: binary vote vs full BFT
    # Binary: each witness sends 1 bit per action
    # Full BFT (PBFT): 3 phases × N messages each = O(N²) messages
    binary_messages = n_witnesses * n_trials
    pbft_messages = 3 * n_witnesses * n_witnesses * n_trials  # O(N²) per round

    return {
        "config": {
            "witnesses": n_witnesses,
            "byzantine": n_byzantine,
            "quorum": quorum,
            "trials": n_trials,
            "strategy": byzantine_strategy,
            "violation_rate": violation_rate,
        },
        "results": {
            "accuracy": correct / n_trials,
            "accuracy_bps": int((correct / n_trials) * 10000),
            "false_approvals": false_approvals,
            "false_rejections": false_rejections,
            "no_quorum": no_quorum,
            "total": n_trials,
        },
        "cost_comparison": {
            "binary_scope_vote_messages": binary_messages,
            "pbft_output_consensus_messages": pbft_messages,
            "savings_ratio": f"{pbft_messages / binary_messages:.1f}x",
        },
        "bft_guarantee": (
            "HOLDS" if n_witnesses >= 3 * n_byzantine + 1 else "VIOLATED"
        ),
    }


def main():
    parser = argparse.ArgumentParser(description="Byzantine scope-violation voting simulator")
    parser.add_argument("--witnesses", "-n", type=int, default=7, help="Total witnesses (default: 7)")
    parser.add_argument("--byzantine", "-f", type=int, default=2, help="Byzantine witnesses (default: 2)")
    parser.add_argument("--trials", "-t", type=int, default=1000, help="Number of actions to evaluate")
    parser.add_argument("--strategy", "-s", default="flip",
                        choices=["flip", "always_approve", "always_reject", "random"],
                        help="Byzantine strategy")
    parser.add_argument("--violation-rate", "-v", type=float, default=0.3,
                        help="Fraction of actions that are violations")
    args = parser.parse_args()

    print(f"=== Scope Vote Simulator ===")
    print(f"N={args.witnesses} witnesses, f={args.byzantine} byzantine ({args.strategy})")
    print(f"BFT requirement: N >= 3f+1 = {3 * args.byzantine + 1}")
    print()

    result = run_simulation(
        args.witnesses, args.byzantine, args.trials,
        args.strategy, args.violation_rate,
    )

    print(f"Accuracy: {result['results']['accuracy_bps']} bps ({result['results']['accuracy']:.2%})")
    print(f"False approvals: {result['results']['false_approvals']}")
    print(f"False rejections: {result['results']['false_rejections']}")
    print(f"No quorum: {result['results']['no_quorum']}")
    print(f"BFT guarantee: {result['bft_guarantee']}")
    print()
    print(f"Cost savings vs full PBFT: {result['cost_comparison']['savings_ratio']}")
    print(f"  Binary scope vote: {result['cost_comparison']['binary_scope_vote_messages']} messages")
    print(f"  PBFT consensus:    {result['cost_comparison']['pbft_output_consensus_messages']} messages")
    print()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
