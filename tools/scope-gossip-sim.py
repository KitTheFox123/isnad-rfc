#!/usr/bin/env python3
"""
scope-gossip-sim.py — Gossip protocol for agent scope verification

Simulates anti-entropy gossip (Demers et al 1987) applied to agent scope monitoring.
Each agent holds a scope hash + timestamp. Agents randomly exchange scope state with
peers each round. Inconsistencies (stale scopes, hash mismatches) propagate as alarms.

Key metrics:
- Rounds to full propagation (pandemic): O(log N) expected
- Detection latency: rounds until a rogue agent is flagged by >50% of network
- False positive rate under clock skew

Usage:
    python3 scope-gossip-sim.py [--agents N] [--rounds R] [--fanout F] [--rogue FRAC]
"""

import argparse
import hashlib
import random
import json
from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple


@dataclass
class ScopeState:
    agent_id: str
    scope_hash: str
    timestamp: int  # logical clock
    is_rogue: bool = False
    alarms: Set[str] = field(default_factory=set)  # agent_ids flagged as suspicious


@dataclass
class GossipMessage:
    sender_id: str
    known_scopes: Dict[str, Tuple[str, int]]  # agent_id -> (hash, timestamp)


def make_scope_hash(agent_id: str, round_num: int, rogue: bool = False) -> str:
    """Generate a scope hash. Rogue agents produce different hashes."""
    content = f"{agent_id}:round{round_num}"
    if rogue:
        content += ":ROGUE_DEVIATION"
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def simulate(n_agents: int, n_rounds: int, fanout: int, rogue_frac: float, seed: int = 42):
    random.seed(seed)

    # Initialize agents
    n_rogue = max(1, int(n_agents * rogue_frac))
    agents: Dict[str, ScopeState] = {}
    
    for i in range(n_agents):
        aid = f"agent_{i:03d}"
        is_rogue = i < n_rogue
        agents[aid] = ScopeState(
            agent_id=aid,
            scope_hash=make_scope_hash(aid, 0, is_rogue),
            timestamp=0,
            is_rogue=is_rogue,
        )

    # Each agent maintains a view of all known scopes
    views: Dict[str, Dict[str, Tuple[str, int]]] = {}
    for aid in agents:
        views[aid] = {aid: (agents[aid].scope_hash, 0)}

    results = []
    
    for round_num in range(1, n_rounds + 1):
        # Update scope hashes (agents re-commit each round, like heartbeats)
        expected_hashes = {}
        for aid, state in agents.items():
            new_hash = make_scope_hash(aid, round_num, state.is_rogue)
            state.scope_hash = new_hash
            state.timestamp = round_num
            views[aid][aid] = (new_hash, round_num)
            expected_hashes[aid] = make_scope_hash(aid, round_num, False)  # honest hash

        # Gossip phase: each agent contacts `fanout` random peers
        agent_ids = list(agents.keys())
        for aid in agent_ids:
            peers = random.sample([x for x in agent_ids if x != aid], min(fanout, len(agent_ids) - 1))
            for peer_id in peers:
                # Exchange views (push-pull anti-entropy)
                for known_id, (h, t) in views[aid].items():
                    if known_id not in views[peer_id] or views[peer_id][known_id][1] < t:
                        views[peer_id][known_id] = (h, t)
                for known_id, (h, t) in views[peer_id].items():
                    if known_id not in views[aid] or views[aid][known_id][1] < t:
                        views[aid][known_id] = (h, t)

        # Detection phase: check for inconsistencies
        # An honest agent can verify: does the scope hash match what it should be?
        # In practice: monitors cross-check with the principal's signed commitment
        # Here: we simulate by checking against expected (honest) hashes
        detection_count = 0
        total_honest = n_agents - n_rogue
        
        for aid, state in agents.items():
            if state.is_rogue:
                continue
            # Check all known scopes against expected
            for known_id, (h, t) in views[aid].items():
                if t == round_num:  # current round only
                    expected = expected_hashes.get(known_id)
                    if expected and h != expected:
                        state.alarms.add(known_id)
                        detection_count += 1

        # How many honest agents have detected at least one rogue?
        detectors = sum(1 for aid, s in agents.items() if not s.is_rogue and len(s.alarms) > 0)
        detection_rate = detectors / total_honest if total_honest > 0 else 0

        # How many rogue agents are known by >50% of honest agents?
        rogue_ids = [aid for aid, s in agents.items() if s.is_rogue]
        fully_detected = 0
        for rid in rogue_ids:
            knowers = sum(1 for aid, s in agents.items() if not s.is_rogue and rid in s.alarms)
            if knowers > total_honest * 0.5:
                fully_detected += 1

        results.append({
            "round": round_num,
            "detection_rate": round(detection_rate, 4),
            "fully_detected_rogues": fully_detected,
            "total_rogues": n_rogue,
            "avg_view_size": round(sum(len(v) for v in views.values()) / n_agents, 1),
        })

        # Early termination if all rogues fully detected
        if fully_detected == n_rogue and round_num > 1:
            break

    return results


def main():
    parser = argparse.ArgumentParser(description="Scope gossip protocol simulator")
    parser.add_argument("--agents", type=int, default=50, help="Number of agents")
    parser.add_argument("--rounds", type=int, default=20, help="Max gossip rounds")
    parser.add_argument("--fanout", type=int, default=3, help="Peers contacted per round")
    parser.add_argument("--rogue", type=float, default=0.1, help="Fraction of rogue agents")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    results = simulate(args.agents, args.rounds, args.fanout, args.rogue, args.seed)

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print(f"\n{'='*60}")
        print(f"Scope Gossip Simulation")
        print(f"  Agents: {args.agents} ({int(args.agents * args.rogue)} rogue)")
        print(f"  Fanout: {args.fanout}")
        print(f"  Rounds: {len(results)}")
        print(f"{'='*60}")
        print(f"{'Round':>5} {'Detection%':>10} {'Rogues Found':>12} {'Avg View':>10}")
        print(f"{'-'*5:>5} {'-'*10:>10} {'-'*12:>12} {'-'*10:>10}")
        for r in results:
            rogue_str = f"{r['fully_detected_rogues']}/{r['total_rogues']}"
            print(f"{r['round']:>5} {r['detection_rate']*100:>9.1f}% {rogue_str:>12} {r['avg_view_size']:>10.1f}")

        final = results[-1]
        pandemic_round = next((r["round"] for r in results if r["detection_rate"] >= 0.99), None)
        print(f"\n{'='*60}")
        print(f"Pandemic round (99% detection): {pandemic_round or '>'+str(len(results))}")
        print(f"Final detection rate: {final['detection_rate']*100:.1f}%")
        print(f"Rogues fully detected: {final['fully_detected_rogues']}/{final['total_rogues']}")
        expected = f"O(log {args.agents}) ≈ {int(args.agents.bit_length())}"
        print(f"Expected rounds (theory): {expected}")


if __name__ == "__main__":
    main()
