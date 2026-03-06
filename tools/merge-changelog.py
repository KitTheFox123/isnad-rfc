#!/usr/bin/env python3
"""Generate merge changelog for isnad-rfc tools branch → main.

Reads all tool .py files, extracts docstrings and key references,
outputs a structured changelog suitable for PR description or NIST submission.
"""

import ast
import os
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).parent

def extract_tool_info(filepath: Path) -> dict:
    """Extract docstring, references, and imports from a tool file."""
    source = filepath.read_text()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {"name": filepath.stem, "doc": "(parse error)", "lines": len(source.splitlines())}
    
    doc = ast.get_docstring(tree) or "(no docstring)"
    # First line = summary
    summary = doc.strip().split('\n')[0]
    
    # Count functions and classes
    funcs = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
    classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
    
    return {
        "name": filepath.stem,
        "summary": summary,
        "full_doc": doc,
        "lines": len(source.splitlines()),
        "functions": len(funcs),
        "classes": len(classes),
    }

def categorize(name: str) -> str:
    """Categorize tool by trust lifecycle phase."""
    scope = ["scope-drift-detector", "procedure_commitment_auditor", "precommit-verifier",
             "commitment_verifier", "event_scope_invalidator", "canary-spec-commit",
             "scope-commit-at-issuance"]
    monitoring = ["mmd-monitor", "proximity_drift_scorer", "semantic_changepoint",
                  "execution-trace-commit"]
    attestation = ["integer-brier-scorer", "response-diversity", "attestation_loafing_detector",
                   "repetition_truth_detector", "friendship-paradox"]
    identity = ["collusion-detector", "exchange-id-antireplay", "selection-gap-detector"]
    
    for cat, names in [("Scope & Commitment", scope), ("Execution Monitoring", monitoring),
                        ("Attestation & Verification", attestation), ("Identity & Anti-Replay", identity)]:
        if name in names:
            return cat
    return "Other"

def main():
    tools = []
    for f in sorted(TOOLS_DIR.glob("*.py")):
        if f.name == "merge-changelog.py":
            continue
        tools.append(extract_tool_info(f))
    
    total_lines = sum(t["lines"] for t in tools)
    total_funcs = sum(t["functions"] for t in tools)
    
    print("# isnad-rfc Tools Branch — Merge Changelog")
    print(f"\n**{len(tools)} tools | {total_lines} lines | {total_funcs} functions**\n")
    
    # Group by category
    by_cat = {}
    for t in tools:
        cat = categorize(t["name"])
        by_cat.setdefault(cat, []).append(t)
    
    for cat in ["Scope & Commitment", "Execution Monitoring", "Attestation & Verification",
                "Identity & Anti-Replay", "Other"]:
        if cat not in by_cat:
            continue
        print(f"\n## {cat}\n")
        for t in by_cat[cat]:
            print(f"### `{t['name']}.py` ({t['lines']} lines, {t['functions']} fns)")
            print(f"{t['summary']}\n")
    
    # Summary stats
    print("\n## Statistics")
    print(f"- Total tools: {len(tools)}")
    print(f"- Total lines: {total_lines}")
    print(f"- Total functions: {total_funcs}")
    print(f"- Avg lines/tool: {total_lines // len(tools)}")
    
    # Research references (scan docstrings for parenthetical citations)
    import re
    refs = set()
    for t in tools:
        found = re.findall(r'\(([A-Z][a-z]+(?:\s+(?:&|et al\.?|and)\s+[A-Z][a-z]+)?\s*,?\s*\d{4}[a-z]?)\)', t["full_doc"])
        refs.update(found)
    
    if refs:
        print(f"\n## Research References ({len(refs)} cited)")
        for r in sorted(refs):
            print(f"- {r}")

if __name__ == "__main__":
    main()
