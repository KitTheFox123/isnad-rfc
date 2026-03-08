#!/usr/bin/env python3
"""
generate-review-summary.py — NIST CAISI Review Summary Generator

Generates a human-readable summary of the isnad-rfc submission package
for pre-submission review. Scans all tools, extracts docstrings, groups
by category, and produces REVIEW-SUMMARY.md.

Usage: python3 tools/generate-review-summary.py
"""

import ast
import subprocess
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).parent.parent
TOOLS_DIR = REPO / "tools"
OUTPUT = REPO / "REVIEW-SUMMARY.md"

# Category keywords for auto-classification
CATEGORIES = {
    "Trust & Attestation": ["attestation", "trust", "isnad", "collusion", "loafing", "brier", "friendship"],
    "Scope & Authorization": ["scope", "commit", "intent", "canary", "event", "drift", "intention"],
    "Identity & Provenance": ["exchange", "execution", "commitment", "provenance", "gossip"],
    "Analysis & Simulation": ["analyzer", "detector", "simulator", "preflight", "manifest", "review", "changelog", "thread", "cost"],
}


def classify_tool(name: str, docstring: str) -> str:
    combined = (name + " " + (docstring or "")).lower()
    scores = {}
    for cat, keywords in CATEGORIES.items():
        scores[cat] = sum(1 for kw in keywords if kw in combined)
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "Other"


def extract_tool_info(path: Path) -> dict:
    try:
        source = path.read_text()
        tree = ast.parse(source)
        docstring = ast.get_docstring(tree) or ""
        lines = len(source.splitlines())
        # First line of docstring as summary
        summary = docstring.split("\n")[0].strip() if docstring else "(no description)"
        return {
            "name": path.stem,
            "file": path.name,
            "summary": summary,
            "docstring": docstring,
            "lines": lines,
        }
    except SyntaxError:
        return {"name": path.stem, "file": path.name, "summary": "(syntax error)", "docstring": "", "lines": 0}


def get_git_info() -> dict:
    try:
        commit = subprocess.check_output(["git", "log", "-1", "--format=%H %s"], cwd=REPO, text=True).strip()
        branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=REPO, text=True).strip()
        return {"commit": commit, "branch": branch}
    except subprocess.CalledProcessError:
        return {"commit": "unknown", "branch": "unknown"}


def main():
    tools = sorted(TOOLS_DIR.glob("*.py"))
    infos = [extract_tool_info(t) for t in tools]

    # Classify
    categorized = defaultdict(list)
    for info in infos:
        cat = classify_tool(info["name"], info["docstring"])
        categorized[cat].append(info)

    git = get_git_info()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    total_lines = sum(i["lines"] for i in infos)

    lines = [
        "# Isnad RFC — Submission Review Summary\n",
        f"*Generated {now} | Branch: {git['branch']} | {git['commit'][:50]}*\n",
        f"## Overview\n",
        f"- **Total tools:** {len(infos)}",
        f"- **Total lines:** {total_lines:,}",
        f"- **Categories:** {len(categorized)}",
        "",
    ]

    for cat in sorted(categorized.keys()):
        cat_tools = categorized[cat]
        lines.append(f"## {cat} ({len(cat_tools)} tools)\n")
        lines.append("| Tool | Lines | Description |")
        lines.append("|------|-------|-------------|")
        for t in sorted(cat_tools, key=lambda x: x["name"]):
            lines.append(f"| `{t['file']}` | {t['lines']} | {t['summary'][:80]} |")
        lines.append("")

    # Key files section
    lines.append("## Key Documents\n")
    key_files = ["NIST-SUBMISSION.md", "README.md", "SUBMISSION-MANIFEST.json", "tools/PRE-MERGE-VALIDATION.md"]
    for f in key_files:
        p = REPO / f
        if p.exists():
            size = p.stat().st_size
            lines.append(f"- **{f}** — {size:,} bytes")
        else:
            lines.append(f"- **{f}** — ⚠️ MISSING")
    lines.append("")

    OUTPUT.write_text("\n".join(lines))
    print(f"Written: {OUTPUT} ({len(infos)} tools, {total_lines:,} lines)")


if __name__ == "__main__":
    main()
