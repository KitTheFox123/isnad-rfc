#!/usr/bin/env python3
"""
nist-review-checklist.py — NIST CAISI Submission Review Checklist

Generates a structured review checklist for the March 8 review day.
Checks each tool against NIST alignment criteria:
1. Has clear threat model (what attack does it detect?)
2. References at least one academic source
3. Produces machine-readable output (JSON/scores)
4. Maps to Human Root of Trust framework levels
5. Has demo/example output in docstring or comments

Usage: python3 tools/nist-review-checklist.py [--verbose]
"""

import ast
import re
import sys
from pathlib import Path

REPO = Path(__file__).parent.parent
TOOLS_DIR = REPO / "tools"

# Keywords indicating threat model awareness
THREAT_KEYWORDS = [
    "attack", "threat", "adversar", "malicious", "collu", "sybil",
    "forgery", "drift", "confused deputy", "injection", "replay",
    "loafing", "free-rid", "split-view", "byzantine", "manipulation",
]

# Keywords indicating academic references
REFERENCE_KEYWORDS = [
    "arxiv", "doi", "isbn", "et al", "journal", "proceedings",
    r"\(\d{4}\)", r"\d{4}\)", "ieee", "acm", "springer", "nature",
    "science", "pnas", "biometrika", "psychol",
]

# Keywords indicating HRoT alignment
HROT_KEYWORDS = [
    "human root", "hrot", "principal", "operator", "delegation",
    "scope", "attestation", "trust chain", "authority",
]

# Keywords indicating machine-readable output
OUTPUT_KEYWORDS = [
    "json", "score", "grade", "metric", "ratio", "percent",
    "dict", "dataclass", "namedtuple",
]


def analyze_tool(path: Path) -> dict:
    """Analyze a single tool against review criteria."""
    source = path.read_text()
    source_lower = source.lower()
    
    try:
        tree = ast.parse(source)
        docstring = ast.get_docstring(tree) or ""
    except SyntaxError:
        return {"name": path.name, "error": "syntax error"}
    
    result = {
        "name": path.name,
        "lines": len(source.split("\n")),
        "has_docstring": bool(docstring),
        "has_threat_model": any(kw in source_lower for kw in THREAT_KEYWORDS),
        "has_references": any(
            re.search(kw, source_lower) for kw in REFERENCE_KEYWORDS
        ),
        "has_machine_output": any(kw in source_lower for kw in OUTPUT_KEYWORDS),
        "has_hrot_alignment": any(kw in source_lower for kw in HROT_KEYWORDS),
        "has_demo": "demo" in source_lower or "example" in source_lower or "if __name__" in source,
    }
    
    # Count criteria met
    criteria = [
        result["has_threat_model"],
        result["has_references"],
        result["has_machine_output"],
        result["has_hrot_alignment"],
        result["has_demo"],
    ]
    result["criteria_met"] = sum(criteria)
    result["grade"] = (
        "A" if result["criteria_met"] >= 5 else
        "B" if result["criteria_met"] >= 4 else
        "C" if result["criteria_met"] >= 3 else
        "D" if result["criteria_met"] >= 2 else "F"
    )
    
    return result


def main():
    verbose = "--verbose" in sys.argv
    tools = sorted(TOOLS_DIR.glob("*.py"))
    
    # Exclude self and other meta-tools
    meta = {"nist-review-checklist.py", "submission-preflight.py", "merge-changelog.py"}
    tools = [t for t in tools if t.name not in meta]
    
    results = [analyze_tool(t) for t in tools]
    
    # Summary
    grades = {"A": 0, "B": 0, "C": 0, "D": 0, "F": 0}
    for r in results:
        grades[r.get("grade", "F")] += 1
    
    print("=" * 65)
    print("NIST CAISI Review Checklist — March 8, 2026")
    print("=" * 65)
    print(f"\nTools analyzed: {len(results)}")
    print(f"Grade distribution: A={grades['A']} B={grades['B']} C={grades['C']} D={grades['D']} F={grades['F']}")
    
    # Criteria coverage
    has_threat = sum(1 for r in results if r.get("has_threat_model"))
    has_refs = sum(1 for r in results if r.get("has_references"))
    has_output = sum(1 for r in results if r.get("has_machine_output"))
    has_hrot = sum(1 for r in results if r.get("has_hrot_alignment"))
    has_demo = sum(1 for r in results if r.get("has_demo"))
    
    print(f"\nCriteria coverage:")
    print(f"  Threat model:      {has_threat}/{len(results)} ({100*has_threat//len(results)}%)")
    print(f"  Academic refs:     {has_refs}/{len(results)} ({100*has_refs//len(results)}%)")
    print(f"  Machine output:    {has_output}/{len(results)} ({100*has_output//len(results)}%)")
    print(f"  HRoT alignment:    {has_hrot}/{len(results)} ({100*has_hrot//len(results)}%)")
    print(f"  Demo/example:      {has_demo}/{len(results)} ({100*has_demo//len(results)}%)")
    
    # Tools needing attention (grade C or below)
    needs_work = [r for r in results if r.get("grade", "F") in ("C", "D", "F")]
    if needs_work:
        print(f"\n⚠️  Tools needing review ({len(needs_work)}):")
        for r in sorted(needs_work, key=lambda x: x.get("criteria_met", 0)):
            missing = []
            if not r.get("has_threat_model"): missing.append("threat")
            if not r.get("has_references"): missing.append("refs")
            if not r.get("has_machine_output"): missing.append("output")
            if not r.get("has_hrot_alignment"): missing.append("hrot")
            if not r.get("has_demo"): missing.append("demo")
            print(f"  {r['grade']} {r['name']:<45} missing: {', '.join(missing)}")
    
    if verbose:
        print(f"\n{'='*65}")
        print("Full tool breakdown:")
        for r in sorted(results, key=lambda x: x["name"]):
            t = "✓" if r.get("has_threat_model") else "·"
            ref = "✓" if r.get("has_references") else "·"
            out = "✓" if r.get("has_machine_output") else "·"
            h = "✓" if r.get("has_hrot_alignment") else "·"
            d = "✓" if r.get("has_demo") else "·"
            print(f"  {r.get('grade','?')} {r['name']:<45} T:{t} R:{ref} O:{out} H:{h} D:{d}  ({r.get('lines',0)}L)")
    
    overall = "A" if grades["A"] + grades["B"] >= len(results) * 0.8 else \
              "B" if grades["F"] == 0 else "C"
    print(f"\n{'='*65}")
    print(f"Overall readiness: Grade {overall}")
    print(f"Review day action: Fix {len(needs_work)} tools needing attention")


if __name__ == "__main__":
    main()
