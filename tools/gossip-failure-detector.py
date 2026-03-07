#!/usr/bin/env python3
"""gossip-failure-detector.py — Gossip-based agent liveness detection.

Based on van Renesse, Minsky & Hayden (1998) "A Gossip-Style Failure Detection Service"
from Cornell. Adapted for agent accountability: heartbeat counters propagated via random
peer exchange, with configurable T_fail and T_cleanup thresholds.

Key properties (from the paper):
1. P(false detection) independent of group size
2. Resilient to message loss and process failures
3. Detection time O(n log n)
4. Bandwidth at most linear in n

Usage:
    python3 gossip-failure-detector.py [--agents N] [--t-gossip SEC] [--t-fail SEC] [--rounds N]
"""

import argparse
import json
import random
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AgentState:
    agent_id: str
    heartbeat: int = 0
    failed: bool = False
    fail_at_round: Optional[int] = None  # simulate crash


@dataclass
class DetectorEntry:
    heartbeat: int = 0
    last_updated: float = 0.0
    suspected: bool = False
    removed: bool = False


@dataclass
class FailureDetector:
    agent_id: str
    t_fail: float
    t_cleanup: float
    members: dict[str, DetectorEntry] = field(default_factory=dict)
    own_heartbeat: int = 0

    def tick(self, current_time: float):
        """Increment own heartbeat counter."""
        self.own_heartbeat += 1
        if self.agent_id not in self.members:
            self.members[self.agent_id] = DetectorEntry()
        self.members[self.agent_id].heartbeat = self.own_heartbeat
        self.members[self.agent_id].last_updated = current_time

    def get_gossip_payload(self) -> dict[str, int]:
        """Return {agent_id: heartbeat} for non-removed members."""
        return {
            aid: entry.heartbeat
            for aid, entry in self.members.items()
            if not entry.removed
        }

    def receive_gossip(self, payload: dict[str, int], current_time: float):
        """Merge received heartbeat counters, adopting maximums."""
        for aid, hb in payload.items():
            if aid not in self.members:
                self.members[aid] = DetectorEntry(heartbeat=hb, last_updated=current_time)
            elif hb > self.members[aid].heartbeat:
                self.members[aid].heartbeat = hb
                self.members[aid].last_updated = current_time
                self.members[aid].suspected = False  # revive if heartbeat advanced

    def check_failures(self, current_time: float) -> list[str]:
        """Check for suspected failures. Returns newly suspected agent IDs."""
        newly_suspected = []
        for aid, entry in self.members.items():
            if aid == self.agent_id or entry.removed:
                continue
            elapsed = current_time - entry.last_updated
            if not entry.suspected and elapsed > self.t_fail:
                entry.suspected = True
                newly_suspected.append(aid)
            elif entry.suspected and elapsed > self.t_cleanup:
                entry.removed = True
        return newly_suspected


def simulate(n_agents: int, t_gossip: float, t_fail: float, n_rounds: int,
             crash_fraction: float = 0.1, message_loss: float = 0.05,
             seed: int = 42):
    """Run gossip failure detection simulation."""
    random.seed(seed)

    # Initialize agents and their detectors
    agents = []
    detectors = {}
    t_cleanup = 2 * t_fail  # van Renesse recommendation

    for i in range(n_agents):
        aid = f"agent_{i:03d}"
        agent = AgentState(agent_id=aid)
        agents.append(agent)
        detectors[aid] = FailureDetector(
            agent_id=aid, t_fail=t_fail, t_cleanup=t_cleanup
        )

    # Schedule some crashes
    n_crash = max(1, int(n_agents * crash_fraction))
    crash_agents = random.sample(agents, n_crash)
    for agent in crash_agents:
        agent.fail_at_round = random.randint(n_rounds // 4, n_rounds // 2)

    # Tracking
    true_positives = 0
    false_positives = 0
    true_negatives = 0
    false_negatives = 0
    detection_delays = []

    crash_times = {}
    detection_times = {}

    for round_num in range(n_rounds):
        current_time = round_num * t_gossip

        # Each live agent: tick + gossip to random peer
        live_agents = [a for a in agents if not a.failed]

        for agent in live_agents:
            # Check if agent crashes this round
            if agent.fail_at_round == round_num:
                agent.failed = True
                crash_times[agent.agent_id] = current_time
                continue

            det = detectors[agent.agent_id]
            det.tick(current_time)

            # Pick random peer to gossip to
            peers = [a for a in agents if a.agent_id != agent.agent_id and not a.failed]
            if not peers:
                continue
            peer = random.choice(peers)

            # Simulate message loss
            if random.random() < message_loss:
                continue

            payload = det.get_gossip_payload()
            detectors[peer.agent_id].receive_gossip(payload, current_time)

        # All live agents check for failures
        for agent in [a for a in agents if not a.failed]:
            det = detectors[agent.agent_id]
            newly_suspected = det.check_failures(current_time)

            for suspected_id in newly_suspected:
                actual_failed = any(
                    a.agent_id == suspected_id and a.failed for a in agents
                )
                if actual_failed:
                    true_positives += 1
                    if suspected_id not in detection_times:
                        detection_times[suspected_id] = current_time
                        delay = current_time - crash_times.get(suspected_id, current_time)
                        detection_delays.append(delay)
                else:
                    false_positives += 1

    # Final accounting
    actually_failed = {a.agent_id for a in agents if a.failed}
    detected_by_any = set(detection_times.keys())
    false_negatives = len(actually_failed - detected_by_any)
    true_negatives = n_agents - len(actually_failed) - false_positives

    results = {
        "config": {
            "n_agents": n_agents,
            "t_gossip": t_gossip,
            "t_fail": t_fail,
            "t_cleanup": t_cleanup,
            "n_rounds": n_rounds,
            "crash_fraction": crash_fraction,
            "message_loss_rate": message_loss,
        },
        "crashes": {
            "total": len(actually_failed),
            "agents": sorted(actually_failed),
            "crash_rounds": {k: v / t_gossip for k, v in crash_times.items()},
        },
        "detection": {
            "true_positives": true_positives,
            "false_positives": false_positives,
            "false_negatives": false_negatives,
            "detected": sorted(detected_by_any),
            "missed": sorted(actually_failed - detected_by_any),
            "mean_detection_delay_rounds": (
                round(sum(detection_delays) / len(detection_delays) / t_gossip, 1)
                if detection_delays else None
            ),
            "max_detection_delay_rounds": (
                round(max(detection_delays) / t_gossip, 1)
                if detection_delays else None
            ),
        },
        "accuracy": {
            "precision": (
                round(true_positives / (true_positives + false_positives), 4)
                if (true_positives + false_positives) > 0 else None
            ),
            "recall": (
                round(true_positives / (true_positives + false_negatives), 4)
                if (true_positives + false_negatives) > 0 else None
            ),
            "false_positive_rate": (
                round(false_positives / max(1, false_positives + true_negatives), 4)
            ),
        },
        "reference": "van Renesse, Minsky & Hayden (1998) 'A Gossip-Style Failure Detection Service', Cornell CS"
    }
    return results


def main():
    parser = argparse.ArgumentParser(description="Gossip-based agent failure detection")
    parser.add_argument("--agents", type=int, default=20, help="Number of agents")
    parser.add_argument("--t-gossip", type=float, default=1.0, help="Gossip interval (sec)")
    parser.add_argument("--t-fail", type=float, default=5.0, help="Failure threshold (sec)")
    parser.add_argument("--rounds", type=int, default=100, help="Simulation rounds")
    parser.add_argument("--crash-fraction", type=float, default=0.1, help="Fraction of agents that crash")
    parser.add_argument("--message-loss", type=float, default=0.05, help="Message loss probability")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    args = parser.parse_args()

    results = simulate(
        n_agents=args.agents,
        t_gossip=args.t_gossip,
        t_fail=args.t_fail,
        n_rounds=args.rounds,
        crash_fraction=args.crash_fraction,
        message_loss=args.message_loss,
        seed=args.seed,
    )
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
