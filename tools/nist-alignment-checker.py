#!/usr/bin/env python3
"""
nist-alignment-checker.py — Maps isnad-rfc tools to NIST AI Agent Standards Initiative pillars.

NIST AI Agent Standards Initiative (Feb 2026) defines three pillars:
1. INTEROPERABILITY — Agent-to-agent communication, protocol standards (A2A, MCP)
2. SECURITY — Identity verification, authorization, audit trails, scope control
3. TESTING & EVALUATION — Behavioral assessment, drift detection, compliance verification

This tool categorizes each isnad tool by NIST pillar alignment and identifies gaps.

Usage: python3 tools/nist-alignment-checker.py [--verbose] [--gaps-only]
"""

import ast
import sys
from pathlib import Path

REPO = Path(__file__).parent.parent
TOOLS_DIR = REPO / "tools"

# NIST AI Agent Standards Initiative pillars (Feb 2026)
PILLARS = {
    "INTEROP": "Interoperability — agent communication, protocol compliance",
    "SECURITY": "Security — identity, authorization, audit trails, scope",
    "TEST_EVAL": "Testing & Evaluation — behavioral assessment, drift, compliance",
}

# Keyword-based classification heuristics
PILLAR_KEYWORDS = {
    "INTEROP": [
        "gossip", "exchange", "protocol", "message", "channel",
        "witness", "communication", "relay",
    ],
    "SECURITY": [
        "attestation", "commitment", "scope", "authorization", "identity",
        "credential", "collusion", "sybil", "deputy", "trust", "canary",
        "provenance", "integrity", "antireplay", "nonce", "sign",
        "human-root", "principal",
    ],
    "TEST_EVAL": [
        "detect", "drift", "score", "brier", "evaluation", "audit",
        "validate", "loafing", "silence", "gap", "intention", "overwrite",
        "fingerprint", "calibrat", "benchmark", "test", "review",
        "preflight", "manifest",
    ],
}


def classify_tool(name: str, docstring: str) -> dict[str, float]:
    """Score a tool against each NIST pillar (0-1)."""
    text = (name + " " + (docstring or "")).lower()
    scores = {}
    for pillar, keywords in PILLAR_KEYWORDS.items():
        hits = sum(1 for kw in keywords if kw in text)
        scores[pillar] = min(1.0, hits / 3)  # normalize: 3+ hits = 1.0
    return scores


def main():
    verbose = "--verbose" in sys.argv
    gaps_only = "--gaps-only" in sys.argv

    tools = sorted(TOOLS_DIR.glob("*.py"))
    results = []

    for tool in tools:
        try:
            tree = ast.parse(tool.read_text())
            docstring = ast.get_docstring(tree) or ""
        except SyntaxError:
            docstring = ""
        scores = classify_tool(tool.stem, docstring)
        primary = max(scores, key=scores.get) if max(scores.values()) > 0 else "UNALIGNED"
        results.append({
            "name": tool.stem,
            "scores": scores,
            "primary": primary,
            "max_score": max(scores.values()),
        })

    # Summary by pillar
    pillar_counts = {p: 0 for p in PILLARS}
    unaligned = []
    for r in results:
        if r["max_score"] > 0:
            pillar_counts[r["primary"]] += 1
        else:
            unaligned.append(r["name"])

    print("=" * 65)
    print("NIST AI Agent Standards Initiative — Isnad Tool Alignment")
    print("=" * 65)
    print(f"\nTotal tools: {len(results)}")
    print()

    for pillar, desc in PILLARS.items():
        count = pillar_counts[pillar]
        bar = "█" * count + "░" * (20 - min(count, 20))
        print(f"  {pillar:12s} [{bar}] {count:2d}  {desc}")

    if unaligned:
        print(f"\n  UNALIGNED: {len(unaligned)} — {', '.join(unaligned[:5])}")

    # Coverage assessment
    print("\n" + "-" * 65)
    total_aligned = sum(pillar_counts.values())
    coverage = {p: c / max(total_aligned, 1) for p, c in pillar_counts.items()}

    gaps = []
    if coverage.get("INTEROP", 0) < 0.15:
        gaps.append("INTEROP: < 15% coverage. Need more protocol/communication tools.")
    if coverage.get("SECURITY", 0) < 0.25:
        gaps.append("SECURITY: < 25% coverage. Core pillar underdeveloped.")
    if coverage.get("TEST_EVAL", 0) < 0.20:
        gaps.append("TEST_EVAL: < 20% coverage. Need more evaluation tools.")

    if gaps:
        print("\n⚠️  GAPS IDENTIFIED:")
        for g in gaps:
            print(f"  - {g}")
    else:
        print("\n✅ All pillars have adequate coverage.")

    # NIST-specific recommendations
    print("\nNIST CAISI Alignment Recommendations:")
    print("  1. Map each tool to NIST AI RMF Govern-Map-Measure-Manage functions")
    print("  2. Cross-reference OWASP Top 10 for LLM (Excessive Agency = scope tools)")
    print("  3. Reference A2A/MCP protocols for interop pillar tools")
    print("  4. Cite humanrootoftrust.org for identity/authorization chain")

    if verbose and not gaps_only:
        print("\n" + "=" * 65)
        print("DETAILED TOOL ALIGNMENT")
        print("=" * 65)
        for r in sorted(results, key=lambda x: x["primary"]):
            scores_str = " | ".join(
                f"{p}={r['scores'][p]:.1f}" for p in PILLARS
            )
            print(f"  {r['name']:40s} → {r['primary']:12s} ({scores_str})")


if __name__ == "__main__":
    main()
