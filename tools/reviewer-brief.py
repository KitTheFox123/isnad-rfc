#!/usr/bin/env python3
"""
reviewer-brief.py — Generate a concise reviewer brief for NIST CAISI submission.

Scans the repo and produces a structured overview:
- Tool inventory with categories and line counts
- Document inventory with word counts
- Key claims extracted from NIST-SUBMISSION.md
- Cross-reference matrix (which tools support which claims)

Output: stdout (markdown) or --json for machine-readable.
"""

import ast
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).parent.parent
TOOLS_DIR = REPO / "tools"

# Tool categories by keyword in docstring
CATEGORIES = {
    "detection": ["detect", "detector", "monitor", "alert", "flag"],
    "verification": ["verify", "verif", "commit", "proof", "valid"],
    "analysis": ["analy", "score", "metric", "measure", "audit"],
    "simulation": ["simul", "model", "scenario", "demo"],
    "infrastructure": ["log", "trace", "manifest", "preflight", "changelog"],
}


def categorize_tool(docstring: str) -> str:
    doc_lower = docstring.lower()
    scores = {}
    for cat, keywords in CATEGORIES.items():
        scores[cat] = sum(1 for kw in keywords if kw in doc_lower)
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "other"


def scan_tools():
    tools = []
    for f in sorted(TOOLS_DIR.glob("*.py")):
        text = f.read_text()
        lines = len(text.splitlines())
        try:
            tree = ast.parse(text)
            docstring = ast.get_docstring(tree) or ""
        except SyntaxError:
            docstring = ""
        category = categorize_tool(docstring)
        tools.append({
            "name": f.stem,
            "lines": lines,
            "category": category,
            "summary": docstring.split("\n")[0][:100] if docstring else "(no docstring)",
        })
    return tools


def scan_docs():
    docs = []
    for ext in ("*.md", "*.txt"):
        for f in sorted(REPO.glob(ext)):
            if f.name.startswith("."):
                continue
            text = f.read_text()
            words = len(text.split())
            docs.append({
                "name": f.name,
                "words": words,
                "lines": len(text.splitlines()),
            })
    return docs


def extract_claims(nist_path: Path) -> list:
    if not nist_path.exists():
        return []
    text = nist_path.read_text()
    claims = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("- **") or line.startswith("* **"):
            claim = re.sub(r"^[-*]\s*\*\*", "", line)
            claim = re.sub(r"\*\*.*", "", claim).strip()
            if len(claim) > 10:
                claims.append(claim)
    return claims[:20]


def main():
    as_json = "--json" in sys.argv
    tools = scan_tools()
    docs = scan_docs()
    claims = extract_claims(REPO / "NIST-SUBMISSION.md")

    # Category summary
    by_cat = defaultdict(list)
    for t in tools:
        by_cat[t["category"]].append(t)

    if as_json:
        print(json.dumps({
            "tool_count": len(tools),
            "total_lines": sum(t["lines"] for t in tools),
            "categories": {k: len(v) for k, v in by_cat.items()},
            "documents": docs,
            "claims": claims,
        }, indent=2))
        return

    print("# NIST CAISI Submission — Reviewer Brief")
    print(f"\n**Generated for review cycle March 8, 2026**\n")

    print(f"## Tool Inventory ({len(tools)} tools, {sum(t['lines'] for t in tools):,} lines)")
    print()
    for cat in sorted(by_cat.keys()):
        cat_tools = by_cat[cat]
        print(f"### {cat.title()} ({len(cat_tools)} tools)")
        for t in cat_tools:
            print(f"- `{t['name']}` ({t['lines']} lines) — {t['summary']}")
        print()

    print(f"## Document Inventory ({len(docs)} files)")
    for d in docs:
        print(f"- `{d['name']}` — {d['words']} words, {d['lines']} lines")

    if claims:
        print(f"\n## Key Claims ({len(claims)})")
        for i, c in enumerate(claims, 1):
            print(f"{i}. {c}")

    print("\n## Submission Health")
    print(f"- Tools with docstrings: {sum(1 for t in tools if t['summary'] != '(no docstring)')}/{len(tools)}")
    print(f"- Categories covered: {len(by_cat)}")
    print(f"- Total codebase: {sum(t['lines'] for t in tools):,} lines across {len(tools)} tools")


if __name__ == "__main__":
    main()
