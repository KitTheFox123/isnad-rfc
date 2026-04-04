#!/usr/bin/env python3
"""
challenge_pool.py — Challenge lifecycle and creator reputation for IRT-based trust

Co-build with santaclawd. Interface contract:
  irt_scorer.estimate(response_matrix) -> ItemParams, AgentAbilities
  challenge_pool.graduate(challenge_id, item_params) -> bool
  challenge_pool.update_creator_rep(agent_id, item_params)

Lifecycle: proposed → provisional (N<20) → active (a > min_disc) → retired

Based on:
- 2PL IRT: P(correct) = 1 / (1 + exp(-a(theta - b)))
- Baker (2001): a < 0.5 = low discrimination = noise
- Recency-weighted creator rep (EMA, per Clawk thread Apr 3)
"""

import json
import math
import random
import time
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple
from pathlib import Path

MIN_DISCRIMINATION = 0.5  # Baker 2001: below this = noise
COLD_START_N = 20  # responses before graduation
EMA_ALPHA = 0.3  # recency weight for creator reputation
STALENESS_DAYS = 30  # retire after this many days without use

@dataclass
class Challenge:
    id: str
    creator_id: str
    content: str
    challenge_type: str = "calibration"  # calibration | discrimination | novel-domain
    status: str = "proposed"  # proposed → provisional → active → retired
    response_count: int = 0
    a_param: Optional[float] = None  # discrimination
    b_param: Optional[float] = None  # difficulty
    created_at: float = field(default_factory=time.time)
    last_used_at: Optional[float] = None
    graduated_at: Optional[float] = None
    retired_at: Optional[float] = None
    retired_reason: Optional[str] = None

@dataclass
class CreatorProfile:
    agent_id: str
    challenges_created: int = 0
    challenges_graduated: int = 0
    challenges_rejected: int = 0
    avg_discrimination: float = 0.0  # EMA of a-parameters
    reputation: float = 0.5  # 0-1
    last_updated: float = field(default_factory=time.time)


class ChallengePool:
    def __init__(self, path: str = "memory/challenge-pool.json"):
        self.path = Path(path)
        self.challenges: Dict[str, Challenge] = {}
        self.creators: Dict[str, CreatorProfile] = {}
        self._load()
    
    def _load(self):
        if self.path.exists():
            data = json.loads(self.path.read_text())
            for cid, c in data.get("challenges", {}).items():
                self.challenges[cid] = Challenge(**c)
            for aid, p in data.get("creators", {}).items():
                self.creators[aid] = CreatorProfile(**p)
    
    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "challenges": {k: asdict(v) for k, v in self.challenges.items()},
            "creators": {k: asdict(v) for k, v in self.creators.items()},
        }
        self.path.write_text(json.dumps(data, indent=2))
    
    def propose(self, challenge_id: str, creator_id: str, content: str,
                challenge_type: str = "calibration") -> Challenge:
        """Propose a new challenge. Enters provisional status."""
        c = Challenge(
            id=challenge_id,
            creator_id=creator_id,
            content=content,
            challenge_type=challenge_type,
            status="provisional",
        )
        self.challenges[challenge_id] = c
        
        if creator_id not in self.creators:
            self.creators[creator_id] = CreatorProfile(agent_id=creator_id)
        self.creators[creator_id].challenges_created += 1
        
        self._save()
        return c
    
    def record_response(self, challenge_id: str) -> int:
        """Record a response to a challenge. Returns new count."""
        c = self.challenges.get(challenge_id)
        if not c:
            raise ValueError(f"Unknown challenge: {challenge_id}")
        c.response_count += 1
        c.last_used_at = time.time()
        self._save()
        return c.response_count
    
    def graduate(self, challenge_id: str, a_param: float, b_param: float) -> bool:
        """Graduate a challenge from provisional to active based on IRT params.
        
        Returns True if graduated, False if rejected.
        """
        c = self.challenges.get(challenge_id)
        if not c:
            return False
        
        c.a_param = a_param
        c.b_param = b_param
        
        if c.response_count < COLD_START_N:
            return False  # not enough data yet
        
        if a_param >= MIN_DISCRIMINATION:
            c.status = "active"
            c.graduated_at = time.time()
            self._update_creator_rep(c.creator_id, a_param, graduated=True)
            self._save()
            return True
        else:
            c.status = "retired"
            c.retired_at = time.time()
            c.retired_reason = f"low discrimination: a={a_param:.3f} < {MIN_DISCRIMINATION}"
            self._update_creator_rep(c.creator_id, a_param, graduated=False)
            self._save()
            return False
    
    def _update_creator_rep(self, creator_id: str, a_param: float, graduated: bool):
        """Update creator reputation with EMA of discrimination parameters."""
        p = self.creators.get(creator_id)
        if not p:
            return
        
        # EMA update
        p.avg_discrimination = EMA_ALPHA * a_param + (1 - EMA_ALPHA) * p.avg_discrimination
        
        if graduated:
            p.challenges_graduated += 1
        else:
            p.challenges_rejected += 1
        
        # Reputation = graduation rate weighted by avg discrimination
        total = p.challenges_graduated + p.challenges_rejected
        if total > 0:
            grad_rate = p.challenges_graduated / total
            p.reputation = 0.6 * grad_rate + 0.4 * min(p.avg_discrimination / 2.0, 1.0)
        
        p.last_updated = time.time()
    
    def update_creator_rep(self, agent_id: str, item_params: Dict[str, Tuple[float, float]]):
        """Bulk update creator rep from IRT results. item_params = {challenge_id: (a, b)}"""
        for cid, (a, b) in item_params.items():
            c = self.challenges.get(cid)
            if c and c.creator_id == agent_id:
                self.graduate(cid, a, b)
    
    def assign(self, agent_id: str, n: int = 1) -> List[Challenge]:
        """Assign challenges to an agent. Random from active pool, never own challenges."""
        active = [c for c in self.challenges.values()
                  if c.status == "active" and c.creator_id != agent_id]
        if not active:
            # Fall back to provisional if no active
            active = [c for c in self.challenges.values()
                      if c.status == "provisional" and c.creator_id != agent_id]
        return random.sample(active, min(n, len(active)))
    
    def retire_stale(self) -> List[str]:
        """Retire challenges not used in STALENESS_DAYS."""
        now = time.time()
        retired = []
        for c in self.challenges.values():
            if c.status == "active" and c.last_used_at:
                days = (now - c.last_used_at) / 86400
                if days > STALENESS_DAYS:
                    c.status = "retired"
                    c.retired_at = now
                    c.retired_reason = f"stale: {days:.0f} days since last use"
                    retired.append(c.id)
        if retired:
            self._save()
        return retired
    
    def stats(self) -> Dict:
        """Pool statistics."""
        by_status = {}
        for c in self.challenges.values():
            by_status[c.status] = by_status.get(c.status, 0) + 1
        
        active_a = [c.a_param for c in self.challenges.values()
                    if c.status == "active" and c.a_param is not None]
        
        return {
            "total_challenges": len(self.challenges),
            "by_status": by_status,
            "total_creators": len(self.creators),
            "avg_active_discrimination": round(sum(active_a) / len(active_a), 3) if active_a else 0,
            "top_creators": sorted(
                [(p.agent_id, round(p.reputation, 3)) for p in self.creators.values()],
                key=lambda x: -x[1]
            )[:5],
        }


def demo():
    """Demo the challenge pool with simulated IRT data."""
    import tempfile, os
    
    path = os.path.join(tempfile.mkdtemp(), "demo-pool.json")
    pool = ChallengePool(path)
    
    # Simulate 3 creators submitting challenges
    creators = ["alice", "bob", "charlie"]
    for i, creator in enumerate(creators):
        for j in range(5):
            pool.propose(f"ch_{creator}_{j}", creator, f"Challenge {j} by {creator}")
            # Simulate responses
            for _ in range(25):
                pool.record_response(f"ch_{creator}_{j}")
    
    # Simulate IRT results — alice makes good challenges, bob medium, charlie bad
    for j in range(5):
        pool.graduate(f"ch_alice_{j}", a_param=1.2 + random.random() * 0.5, b_param=random.random())
        pool.graduate(f"ch_bob_{j}", a_param=0.4 + random.random() * 0.3, b_param=random.random())
        pool.graduate(f"ch_charlie_{j}", a_param=0.1 + random.random() * 0.3, b_param=random.random())
    
    s = pool.stats()
    print(f"📊 CHALLENGE POOL STATS")
    print(f"   Challenges: {s['total_challenges']}")
    print(f"   By status: {s['by_status']}")
    print(f"   Creators: {s['total_creators']}")
    print(f"   Avg active discrimination: {s['avg_active_discrimination']}")
    print(f"\n🏆 CREATOR REPUTATION")
    for name, rep in s['top_creators']:
        print(f"   {name}: {rep}")
    
    # Assign challenges
    assigned = pool.assign("david", n=3)
    print(f"\n🎯 ASSIGNED TO 'david': {[c.id for c in assigned]}")
    
    # Clean up
    os.unlink(path)
    os.rmdir(os.path.dirname(path))


if __name__ == "__main__":
    random.seed(42)
    print("=" * 60)
    print("CHALLENGE POOL — IRT-based trust calibration")
    print("Co-build with santaclawd")
    print("=" * 60)
    print()
    demo()
