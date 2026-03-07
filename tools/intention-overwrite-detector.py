#!/usr/bin/env python3
"""
intention-overwrite-detector.py — Detect incomplete intention deactivation in agent scope transitions.

Based on prospective memory research:
- Scullin et al. 2011: Older adults fail to deactivate completed intentions (PMC12320516)
- Nature HSS 2024: New PM intentions reduce commission errors via intention overwriting
- Möschl et al. 2020: Systematic review of PM aftereffects

The Problem:
When an agent's scope changes (new HEARTBEAT.md, new task assignment), old scope
directives may linger in context and trigger "commission errors" — executing actions
from a completed/cancelled scope. This is the agent equivalent of taking medicine twice.

The Solution:
1. Parse scope transitions (old scope → new scope)
2. Detect "lingering cues" — old scope directives still present in active context
3. Generate explicit "if-then" suppression rules (implementation intentions)
   to overwrite old scope associations
4. Score the overwrite strength based on cue similarity

Key insight from the research:
- Similar old/new cues → MORE commission errors (attentional dependence)
- Dissimilar old/new cues + implementation intentions → FEWER commission errors
- New intentions overwrite old cue-action associations (intention overwriting hypothesis)

Usage:
    python intention-overwrite-detector.py --old-scope old_heartbeat.md --new-scope new_heartbeat.md
    python intention-overwrite-detector.py --scope-log scope_transitions.jsonl
    python intention-overwrite-detector.py --demo
"""

import argparse
import json
import hashlib
import re
import sys
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class ScopeDirective:
    """A single actionable directive from a scope document."""
    text: str
    action_verb: str  # e.g., "post", "check", "build", "reply"
    cue: str  # trigger condition, e.g., "every heartbeat", "if DM received"
    target: str  # what to act on, e.g., "Moltbook", "Clawk", "email"
    hash: str = ""

    def __post_init__(self):
        self.hash = hashlib.sha256(self.text.encode()).hexdigest()[:12]


@dataclass
class CommissionRisk:
    """Risk assessment for a lingering old directive."""
    old_directive: ScopeDirective
    similarity_score: float  # 0-1, higher = more similar to new scope directives
    cue_overlap: float  # 0-1, how much the trigger conditions overlap
    action_overlap: float  # 0-1, how much the actions overlap
    risk_level: str  # LOW, MEDIUM, HIGH, CRITICAL
    suppression_rule: str  # "if-then" implementation intention to prevent commission error
    explanation: str


@dataclass
class OverwriteAnalysis:
    """Full analysis of a scope transition."""
    timestamp: str
    old_scope_hash: str
    new_scope_hash: str
    old_directives: list
    new_directives: list
    commission_risks: list
    overwrite_strength: float  # 0-1, how effectively new scope overwrites old
    recommendation: str


# Common action verbs in agent scopes
ACTION_VERBS = {
    "check", "post", "reply", "build", "search", "fetch", "send", "read",
    "write", "update", "create", "delete", "monitor", "scan", "engage",
    "follow", "like", "comment", "research", "analyze", "verify", "submit",
    "notify", "report", "spawn", "deploy", "install", "review", "approve"
}

# Common targets/platforms
TARGETS = {
    "moltbook", "clawk", "shellmates", "lobchan", "email", "agentmail",
    "telegram", "github", "keenable", "heartbeat", "memory", "discord",
    "twitter", "feed", "inbox", "dm", "notifications"
}


def extract_directives(scope_text: str) -> list[ScopeDirective]:
    """Extract actionable directives from a scope document (e.g., HEARTBEAT.md)."""
    directives = []
    lines = scope_text.split("\n")

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        # Skip pure comments/notes
        if line.startswith("*") and line.endswith("*"):
            continue

        # Find action verbs
        lower = line.lower()
        found_verb = ""
        for verb in ACTION_VERBS:
            if verb in lower:
                found_verb = verb
                break

        if not found_verb:
            continue

        # Find target
        found_target = ""
        for target in TARGETS:
            if target in lower:
                found_target = target
                break

        # Extract cue (trigger condition)
        cue = "implicit"
        cue_patterns = [
            (r"every\s+heartbeat", "every heartbeat"),
            (r"if\s+.{5,40}", None),  # extract the condition
            (r"when\s+.{5,40}", None),
            (r"\(every\s+\w+\)", None),
            (r"always", "always"),
            (r"never", "never"),
            (r"periodically", "periodically"),
        ]
        for pattern, default_cue in cue_patterns:
            match = re.search(pattern, lower)
            if match:
                cue = default_cue or match.group(0)
                break

        directives.append(ScopeDirective(
            text=line[:200],
            action_verb=found_verb,
            cue=cue,
            target=found_target or "general",
        ))

    return directives


def compute_similarity(d1: ScopeDirective, d2: ScopeDirective) -> tuple[float, float, float]:
    """Compute similarity between two directives. Returns (overall, cue_overlap, action_overlap)."""
    # Action similarity
    action_sim = 1.0 if d1.action_verb == d2.action_verb else 0.0

    # Target similarity
    target_sim = 1.0 if d1.target == d2.target else 0.0

    # Cue similarity (simple word overlap)
    words1 = set(d1.cue.lower().split())
    words2 = set(d2.cue.lower().split())
    if words1 and words2:
        cue_sim = len(words1 & words2) / max(len(words1 | words2), 1)
    else:
        cue_sim = 0.0

    # Text similarity (Jaccard on words)
    text_words1 = set(re.findall(r'\w+', d1.text.lower()))
    text_words2 = set(re.findall(r'\w+', d2.text.lower()))
    if text_words1 and text_words2:
        text_sim = len(text_words1 & text_words2) / max(len(text_words1 | text_words2), 1)
    else:
        text_sim = 0.0

    overall = (action_sim * 0.3 + target_sim * 0.3 + cue_sim * 0.2 + text_sim * 0.2)
    return overall, cue_sim, action_sim


def generate_suppression_rule(old: ScopeDirective) -> str:
    """Generate an implementation intention to suppress an old directive.

    Based on Gollwitzer 1999: "if situation X occurs, then I will NOT perform Y"
    and Nature HSS 2024: if-then encoding overwrites old cue-action associations.
    """
    return f'IF "{old.cue}" triggers recall of "{old.action_verb} {old.target}", THEN ignore — scope expired (hash: {old.hash})'


def assess_risk(similarity: float, cue_overlap: float, action_overlap: float) -> str:
    """Assess commission error risk level."""
    # High similarity = high risk (Walser et al. 2012, 2017)
    # Similar cues are easily confused
    if similarity >= 0.7:
        return "CRITICAL"
    elif similarity >= 0.5:
        return "HIGH"
    elif similarity >= 0.3:
        return "MEDIUM"
    else:
        return "LOW"


def analyze_transition(old_scope: str, new_scope: str) -> OverwriteAnalysis:
    """Analyze a scope transition for commission error risks."""
    old_directives = extract_directives(old_scope)
    new_directives = extract_directives(new_scope)

    old_hash = hashlib.sha256(old_scope.encode()).hexdigest()[:12]
    new_hash = hashlib.sha256(new_scope.encode()).hexdigest()[:12]

    risks = []

    for old_d in old_directives:
        # Check if this old directive has a similar replacement in new scope
        max_sim = 0.0
        max_cue = 0.0
        max_action = 0.0

        for new_d in new_directives:
            sim, cue_ov, action_ov = compute_similarity(old_d, new_d)
            if sim > max_sim:
                max_sim = sim
                max_cue = cue_ov
                max_action = action_ov

        # Old directives NOT in new scope are the dangerous ones
        # They linger without explicit deactivation
        if max_sim < 0.8:  # Not clearly replaced
            risk_level = assess_risk(max_sim, max_cue, max_action)

            if max_sim < 0.2:
                explanation = (
                    f"Old directive '{old_d.action_verb} {old_d.target}' has NO equivalent in new scope. "
                    f"Risk: spontaneous retrieval of completed intention when cue '{old_d.cue}' appears in context. "
                    f"(Scullin et al. 2011: older/degraded systems fail to deactivate completed intentions)"
                )
            elif max_sim < 0.5:
                explanation = (
                    f"Old directive partially overlaps with new scope (sim={max_sim:.2f}). "
                    f"Dissimilar enough to avoid confusion, but cue may still trigger old association. "
                    f"(Anderson & Einstein 2017: dissimilar new intentions reduce but don't eliminate commission errors)"
                )
            else:
                explanation = (
                    f"Old directive SIMILAR to new scope directive (sim={max_sim:.2f}). "
                    f"HIGH confusion risk — similar cues easily mistaken for new scope. "
                    f"(Walser et al. 2017: similar old/new PM cues increase commission errors)"
                )

            risks.append(CommissionRisk(
                old_directive=old_d,
                similarity_score=max_sim,
                cue_overlap=max_cue,
                action_overlap=max_action,
                risk_level=risk_level,
                suppression_rule=generate_suppression_rule(old_d),
                explanation=explanation,
            ))

    # Compute overwrite strength
    if old_directives:
        replaced = sum(1 for d in old_directives
                      if any(compute_similarity(d, nd)[0] >= 0.8 for nd in new_directives))
        overwrite_strength = replaced / len(old_directives)
    else:
        overwrite_strength = 1.0

    # Recommendation
    critical_count = sum(1 for r in risks if r.risk_level in ("CRITICAL", "HIGH"))
    if critical_count == 0 and overwrite_strength > 0.7:
        recommendation = "CLEAN TRANSITION: New scope effectively overwrites old directives."
    elif critical_count <= 2:
        recommendation = (
            f"PARTIAL OVERWRITE: {critical_count} high-risk lingering directives. "
            f"Add explicit suppression rules to new scope."
        )
    else:
        recommendation = (
            f"DANGEROUS TRANSITION: {critical_count} high-risk lingering directives. "
            f"Old scope strongly persists. Consider explicit cancellation ceremony "
            f"(Scullin et al. 2009: 'finished' instructions alone don't prevent spontaneous retrieval in degraded systems)."
        )

    return OverwriteAnalysis(
        timestamp=datetime.now(timezone.utc).isoformat(),
        old_scope_hash=old_hash,
        new_scope_hash=new_hash,
        old_directives=[asdict(d) for d in old_directives],
        new_directives=[asdict(d) for d in new_directives],
        commission_risks=[asdict(r) for r in risks],
        overwrite_strength=overwrite_strength,
        recommendation=recommendation,
    )


def demo():
    """Run a demo analysis with sample scope documents."""
    old_scope = """# HEARTBEAT.md (v1 - January)

## Tasks
- Check Moltbook DMs every heartbeat
- Post to m/general (30 min cooldown)
- Reply to Clawk mentions
- Build one script per heartbeat
- Monitor lobchan /unsupervised/ for new threads
- Send daily digest to Telegram
- Check Shellmates discover endpoint
"""

    new_scope = """# HEARTBEAT.md (v2 - February)

## Tasks
- Check Moltbook DMs every heartbeat
- Post research-backed content to m/general (quality gate!)
- Reply to Clawk mentions with Keenable research
- Build one tool per heartbeat (scripts/ directory)
- Check email inbox every heartbeat
- Send heartbeat summary to Telegram
- Welcome new moltys in m/introductions
"""

    print("=" * 70)
    print("INTENTION OVERWRITE DETECTOR — Demo Analysis")
    print("=" * 70)
    print()

    analysis = analyze_transition(old_scope, new_scope)

    print(f"Old scope hash: {analysis.old_scope_hash}")
    print(f"New scope hash: {analysis.new_scope_hash}")
    print(f"Old directives: {len(analysis.old_directives)}")
    print(f"New directives: {len(analysis.new_directives)}")
    print(f"Overwrite strength: {analysis.overwrite_strength:.1%}")
    print()

    if analysis.commission_risks:
        print(f"⚠️  COMMISSION RISKS ({len(analysis.commission_risks)} detected):")
        print("-" * 50)
        for risk_dict in analysis.commission_risks:
            d = risk_dict["old_directive"]
            print(f"\n  [{risk_dict['risk_level']}] {d['action_verb']} {d['target']}")
            print(f"  Similarity to new scope: {risk_dict['similarity_score']:.2f}")
            print(f"  {risk_dict['explanation']}")
            print(f"  Suppression rule: {risk_dict['suppression_rule']}")
    else:
        print("✅ No commission risks detected.")

    print()
    print(f"📋 RECOMMENDATION: {analysis.recommendation}")
    print()

    return analysis


def main():
    parser = argparse.ArgumentParser(
        description="Detect incomplete intention deactivation in agent scope transitions"
    )
    parser.add_argument("--old-scope", help="Path to old scope document")
    parser.add_argument("--new-scope", help="Path to new scope document")
    parser.add_argument("--scope-log", help="Path to JSONL scope transition log")
    parser.add_argument("--demo", action="store_true", help="Run demo analysis")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    if args.demo:
        analysis = demo()
        if args.json:
            print(json.dumps(asdict(analysis) if hasattr(analysis, '__dataclass_fields__') else analysis.__dict__, indent=2))
        return

    if args.old_scope and args.new_scope:
        with open(args.old_scope) as f:
            old_scope = f.read()
        with open(args.new_scope) as f:
            new_scope = f.read()

        analysis = analyze_transition(old_scope, new_scope)

        if args.json:
            print(json.dumps(asdict(analysis), indent=2))
        else:
            print(f"Overwrite strength: {analysis.overwrite_strength:.1%}")
            print(f"Commission risks: {len(analysis.commission_risks)}")
            for r in analysis.commission_risks:
                print(f"  [{r['risk_level']}] {r['old_directive']['text'][:80]}")
            print(f"\n{analysis.recommendation}")
        return

    if args.scope_log:
        print("Scope log analysis not yet implemented. Use --old-scope and --new-scope.")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
