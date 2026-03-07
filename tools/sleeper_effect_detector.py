#!/usr/bin/env python3
"""sleeper_effect_detector.py — Detect sleeper effect patterns in attestation trust.

The sleeper effect (Hovland 1949, Kumkale & Albarracín 2004): messages from
noncredible sources become MORE persuasive over time as source memory fades
but content persists. In agent trust: an attestation's provenance fades while
its claim persists, creating unattributed "truths."

Detects:
1. Source decay: attestations losing provenance over time
2. Content persistence: claims surviving without attribution
3. Dissociation risk: source-content link weakening
4. Cryptomnesia risk: unattributed claims entering shared context

Based on Kumkale & Albarracín (2004) meta-analysis of 72 studies.
Key finding: d+=0.25 when discounting cue follows message + high elaboration.
"""

import json
import hashlib
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Attestation:
    claim: str
    source: str
    timestamp: datetime
    source_credibility: float = 0.5  # 0-1
    content_hash: str = ""
    
    def __post_init__(self):
        if not self.content_hash:
            self.content_hash = hashlib.sha256(self.claim.encode()).hexdigest()[:16]


@dataclass
class SleeperEffectAnalysis:
    """Analyze attestation set for sleeper effect vulnerability."""
    
    attestations: list = field(default_factory=list)
    
    def source_decay_rate(self, window_days: int = 7) -> dict:
        """Measure how quickly source info becomes inaccessible.
        
        Simulates differential decay: content persists, source fades.
        Based on Pratkanis et al 1988: cue-after-message = fastest decay.
        """
        now = datetime.now()
        results = []
        
        for att in self.attestations:
            age_days = (now - att.timestamp).days
            # Source memory decays faster than content (Hovland & Weiss 1951)
            # Exponential decay with half-life of ~14 days for source
            source_retention = 0.5 ** (age_days / 14)
            # Content decays slower, half-life ~42 days
            content_retention = 0.5 ** (age_days / 42)
            
            dissociation = content_retention - source_retention
            
            results.append({
                "claim": att.claim[:60],
                "source": att.source,
                "age_days": age_days,
                "source_retention": round(source_retention, 3),
                "content_retention": round(content_retention, 3),
                "dissociation_risk": round(dissociation, 3),
                "sleeper_vulnerable": dissociation > 0.3
            })
        
        return {
            "attestations": results,
            "avg_dissociation": round(
                sum(r["dissociation_risk"] for r in results) / max(len(results), 1), 3
            ),
            "vulnerable_count": sum(1 for r in results if r["sleeper_vulnerable"])
        }
    
    def cryptomnesia_risk(self) -> dict:
        """Detect claims that persist without attribution.
        
        Johnson et al 1993: source monitoring is reconstructive, not stored.
        Agents have no episodic encoding — everything is cryptomnesia by default.
        """
        # Group by content hash to find repeated claims
        claim_sources = {}
        for att in self.attestations:
            h = att.content_hash
            if h not in claim_sources:
                claim_sources[h] = []
            claim_sources[h].append(att.source)
        
        risks = []
        for h, sources in claim_sources.items():
            unique_sources = set(sources)
            # Single-source claims are highest risk
            risk = 1.0 if len(unique_sources) == 1 else 1.0 / len(unique_sources)
            att = next(a for a in self.attestations if a.content_hash == h)
            risks.append({
                "claim": att.claim[:60],
                "source_count": len(unique_sources),
                "sources": list(unique_sources),
                "cryptomnesia_risk": round(risk, 3)
            })
        
        high_risk = [r for r in risks if r["cryptomnesia_risk"] > 0.7]
        return {
            "claims": risks,
            "high_risk_count": len(high_risk),
            "total_claims": len(risks)
        }
    
    def grade(self) -> dict:
        """Overall sleeper effect vulnerability grade."""
        decay = self.source_decay_rate()
        crypto = self.cryptomnesia_risk()
        
        # Composite score: higher = more vulnerable
        avg_dissociation = decay["avg_dissociation"]
        crypto_ratio = crypto["high_risk_count"] / max(crypto["total_claims"], 1)
        
        composite = (avg_dissociation * 0.6) + (crypto_ratio * 0.4)
        
        if composite < 0.1:
            letter = "A"
        elif composite < 0.2:
            letter = "B"
        elif composite < 0.35:
            letter = "C"
        elif composite < 0.5:
            letter = "D"
        else:
            letter = "F"
        
        return {
            "grade": letter,
            "composite_score": round(composite, 3),
            "dissociation_component": round(avg_dissociation, 3),
            "cryptomnesia_component": round(crypto_ratio, 3),
            "recommendation": self._recommend(letter)
        }
    
    def _recommend(self, grade: str) -> str:
        recs = {
            "A": "Low sleeper effect risk. Source-content binding is fresh.",
            "B": "Moderate risk. Consider refreshing source attestations.",
            "C": "Elevated risk. Some claims losing provenance. Re-attest.",
            "D": "High risk. Source memory fading. Content persisting unattributed.",
            "F": "Critical. Claims floating free of sources. Cryptomnesia active."
        }
        return recs.get(grade, "Unknown")


def demo():
    """Demo with sample attestations."""
    now = datetime.now()
    
    analyzer = SleeperEffectAnalysis(attestations=[
        Attestation("Agent X completed task Y within scope", "operator_alice",
                    now - timedelta(days=1), 0.9),
        Attestation("Agent X completed task Y within scope", "witness_bob",
                    now - timedelta(days=1), 0.7),
        Attestation("System Z is trustworthy for payments", "auditor_carol",
                    now - timedelta(days=30), 0.8),
        Attestation("Protocol W handles edge cases correctly", "unknown_source",
                    now - timedelta(days=60), 0.3),
    ])
    
    print("=== Sleeper Effect Detector ===")
    print(f"Based on Kumkale & Albarracín (2004), 72 studies\n")
    
    decay = analyzer.source_decay_rate()
    print("Source Decay Analysis:")
    for r in decay["attestations"]:
        status = "⚠️ VULNERABLE" if r["sleeper_vulnerable"] else "✓ OK"
        print(f"  [{status}] {r['claim']} (age: {r['age_days']}d, "
              f"source_ret: {r['source_retention']}, dissociation: {r['dissociation_risk']})")
    
    print(f"\nAvg dissociation: {decay['avg_dissociation']}")
    print(f"Vulnerable attestations: {decay['vulnerable_count']}/{len(decay['attestations'])}")
    
    crypto = analyzer.cryptomnesia_risk()
    print(f"\nCryptomnesia Risk:")
    for r in crypto["claims"]:
        print(f"  {r['claim']} — {r['source_count']} source(s), risk: {r['cryptomnesia_risk']}")
    
    grade = analyzer.grade()
    print(f"\n{'='*40}")
    print(f"Grade: {grade['grade']} (composite: {grade['composite_score']})")
    print(f"  Dissociation: {grade['dissociation_component']}")
    print(f"  Cryptomnesia: {grade['cryptomnesia_component']}")
    print(f"  {grade['recommendation']}")


if __name__ == "__main__":
    demo()
