#!/usr/bin/env python3
"""credible_commitment_analyzer.py — Tool #20 for isnad-rfc.

Analyzes agent delegation chains for credible commitment properties.
Based on Schelling (1960), Elster (2000), and CLR's program equilibria framework
(Tennenholtz 2004, JesseClifton/CLR 2019).

A commitment is credible when the committer has removed the option to defect.
For agent scopes: publish hash before action, verify after. Repeated heartbeats
build reputation that makes one-shot non-credible threats into credible ones.

Checks:
1. Pre-commitment: Was scope published BEFORE action?
2. Binding strength: Can the agent retroactively modify the commitment?
3. Transparency: Is the scope publicly verifiable?
4. Repetition credibility: Does track record make future commitments credible?
5. Subgame perfection: Would a rational agent actually enforce the stated penalty?

References:
- Schelling (1960) "Strategy of Conflict" — bridge-burning as credibility
- Elster (2000) "Ulysses Unbound" — precommitment typology
- Tennenholtz (2004) — program equilibria, mutual transparency enables cooperation
- CLR/Clifton (2019) — credibility in TAI systems
- Sobel (1985) — reputation in repeated games
"""

import json
import hashlib
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CommitmentEvent:
    """A single commitment in a delegation chain."""
    scope_hash: str
    timestamp: float
    action_timestamp: Optional[float] = None
    action_hash: Optional[str] = None
    witnesses: list = field(default_factory=list)
    public: bool = False
    binding_mechanism: str = "none"  # none, hash, signature, multisig, smart_contract


@dataclass
class CommitmentAnalysis:
    """Results of analyzing a commitment chain."""
    precommitment_score: float = 0.0  # Was scope published before action?
    binding_score: float = 0.0  # Can agent retroactively modify?
    transparency_score: float = 0.0  # Is scope publicly verifiable?
    repetition_score: float = 0.0  # Does track record help?
    subgame_perfect: bool = False  # Would rational agent enforce penalty?
    composite_score: float = 0.0
    grade: str = "F"
    details: dict = field(default_factory=dict)


def analyze_precommitment(events: list[CommitmentEvent]) -> float:
    """Check if scope was published before action (Schelling bridge-burning)."""
    if not events:
        return 0.0
    valid = sum(1 for e in events
                if e.action_timestamp and e.timestamp < e.action_timestamp)
    return valid / len(events)


def analyze_binding(events: list[CommitmentEvent]) -> float:
    """Assess binding strength of commitment mechanism."""
    mechanism_scores = {
        "none": 0.0,
        "hash": 0.3,  # Can verify but not enforce
        "signature": 0.5,  # Non-repudiable but revocable
        "multisig": 0.8,  # Multiple parties must collude to break
        "smart_contract": 0.95,  # Code-enforced, nearly irrevocable
    }
    if not events:
        return 0.0
    scores = [mechanism_scores.get(e.binding_mechanism, 0.0) for e in events]
    return sum(scores) / len(scores)


def analyze_transparency(events: list[CommitmentEvent]) -> float:
    """Check if commitments are publicly verifiable (program games transparency)."""
    if not events:
        return 0.0
    public_count = sum(1 for e in events if e.public)
    witnessed_count = sum(1 for e in events if len(e.witnesses) > 0)
    # Tennenholtz: mutual transparency enables cooperation
    return (public_count + witnessed_count) / (2 * len(events))


def analyze_repetition(events: list[CommitmentEvent]) -> float:
    """Assess reputation from repeated credible commitments (Sobel 1985).

    In repeated games, agents establish credibility by consistently
    making good on claims. Each fulfilled commitment increases credibility.
    """
    if len(events) < 2:
        return 0.0
    fulfilled = sum(1 for e in events if e.action_hash is not None)
    # Sobel: credibility builds logarithmically with track record
    import math
    raw = fulfilled / len(events)
    # Logarithmic scaling: first few fulfillments matter most
    return min(1.0, math.log1p(raw * len(events)) / math.log1p(len(events)))


def check_subgame_perfection(events: list[CommitmentEvent]) -> bool:
    """Would a rational agent actually enforce the stated penalty?

    SPE says threats are never carried out in one-shot games because
    the threatener has no incentive post-refusal. But with:
    1. Reputation effects (repeated game)
    2. Automated enforcement (smart contracts)
    3. Sunk costs in commitment device
    ...the threat becomes credible.
    """
    if not events:
        return False
    # Credible if: repeated (rep effects) OR automated (can't choose not to enforce)
    has_reputation = len(events) >= 3
    has_automation = any(e.binding_mechanism in ("smart_contract", "multisig")
                        for e in events)
    return has_reputation or has_automation


def grade(score: float) -> str:
    if score >= 0.9:
        return "A"
    elif score >= 0.8:
        return "B"
    elif score >= 0.7:
        return "C"
    elif score >= 0.6:
        return "D"
    return "F"


def analyze_chain(events: list[CommitmentEvent]) -> CommitmentAnalysis:
    """Full analysis of a commitment chain."""
    precommit = analyze_precommitment(events)
    binding = analyze_binding(events)
    transparency = analyze_transparency(events)
    repetition = analyze_repetition(events)
    sperfect = check_subgame_perfection(events)

    # Weighted composite
    # Pre-commitment is most important (Schelling: the bridge must actually burn)
    composite = (
        0.30 * precommit +
        0.25 * binding +
        0.20 * transparency +
        0.15 * repetition +
        0.10 * (1.0 if sperfect else 0.0)
    )

    return CommitmentAnalysis(
        precommitment_score=precommit,
        binding_score=binding,
        transparency_score=transparency,
        repetition_score=repetition,
        subgame_perfect=sperfect,
        composite_score=composite,
        grade=grade(composite),
        details={
            "n_events": len(events),
            "mechanisms": [e.binding_mechanism for e in events],
            "framework": "Schelling/Elster/Tennenholtz/CLR",
        }
    )


def demo():
    """Demonstrate with sample commitment chains."""
    now = time.time()

    # Scenario 1: Strong commitment chain (like isnad test case 3)
    strong = [
        CommitmentEvent(
            scope_hash=hashlib.sha256(b"scope_v1").hexdigest()[:16],
            timestamp=now - 3600,
            action_timestamp=now - 3500,
            action_hash=hashlib.sha256(b"action_v1").hexdigest()[:16],
            witnesses=["bro_agent", "gendolf"],
            public=True,
            binding_mechanism="signature",
        ),
        CommitmentEvent(
            scope_hash=hashlib.sha256(b"scope_v2").hexdigest()[:16],
            timestamp=now - 2400,
            action_timestamp=now - 2300,
            action_hash=hashlib.sha256(b"action_v2").hexdigest()[:16],
            witnesses=["santaclawd"],
            public=True,
            binding_mechanism="multisig",
        ),
        CommitmentEvent(
            scope_hash=hashlib.sha256(b"scope_v3").hexdigest()[:16],
            timestamp=now - 1200,
            action_timestamp=now - 1100,
            action_hash=hashlib.sha256(b"action_v3").hexdigest()[:16],
            witnesses=["braindiff", "momo"],
            public=True,
            binding_mechanism="multisig",
        ),
    ]

    # Scenario 2: Weak chain (self-signed, no witnesses, post-hoc)
    weak = [
        CommitmentEvent(
            scope_hash=hashlib.sha256(b"late_scope").hexdigest()[:16],
            timestamp=now - 100,  # AFTER action
            action_timestamp=now - 200,
            action_hash=hashlib.sha256(b"action").hexdigest()[:16],
            witnesses=[],
            public=False,
            binding_mechanism="none",
        ),
    ]

    print("=== Credible Commitment Analyzer ===")
    print("Based on Schelling/Elster/Tennenholtz/CLR\n")

    for name, chain in [("Strong (isnad-like)", strong), ("Weak (self-signed)", weak)]:
        result = analyze_chain(chain)
        print(f"--- {name} ---")
        print(f"  Pre-commitment: {result.precommitment_score:.2f}")
        print(f"  Binding:        {result.binding_score:.2f}")
        print(f"  Transparency:   {result.transparency_score:.2f}")
        print(f"  Repetition:     {result.repetition_score:.2f}")
        print(f"  SPE-credible:   {result.subgame_perfect}")
        print(f"  Composite:      {result.composite_score:.3f} → Grade {result.grade}")
        print()


if __name__ == "__main__":
    demo()
