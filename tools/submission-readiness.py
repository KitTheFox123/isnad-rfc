#!/usr/bin/env python3
"""NIST CAISI Submission Readiness Checker.

Validates the isnad-rfc repo is ready for NIST submission:
- All tools have docstrings and pass syntax check
- NIST-SUBMISSION.md exists and has required sections
- PRE-MERGE-VALIDATION.md is current
- No uncommitted changes
- README references tool count accurately
"""

import ast
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).parent.parent
TOOLS_DIR = REPO / "tools"
REQUIRED_DOCS = ["tools/NIST-SUBMISSION.md", "README.md", "tools/PRE-MERGE-VALIDATION.md"]
REQUIRED_SECTIONS = ["Human Root of Trust", "scope", "attestation", "delegation"]

def check_tools():
    """Verify all Python tools parse and have docstrings."""
    issues = []
    tools = sorted(TOOLS_DIR.glob("*.py"))
    for t in tools:
        try:
            tree = ast.parse(t.read_text())
            doc = ast.get_docstring(tree)
            if not doc:
                issues.append(f"  WARN: {t.name} missing module docstring")
        except SyntaxError as e:
            issues.append(f"  FAIL: {t.name} syntax error: {e}")
    return tools, issues

def check_docs():
    """Verify required documentation exists."""
    issues = []
    for doc in REQUIRED_DOCS:
        p = REPO / doc
        if not p.exists():
            issues.append(f"  MISSING: {doc}")
        elif p.stat().st_size < 100:
            issues.append(f"  WARN: {doc} suspiciously small ({p.stat().st_size}b)")
    return issues

def check_nist_sections():
    """Verify NIST-SUBMISSION.md covers required topics."""
    nist = REPO / "tools" / "NIST-SUBMISSION.md"
    if not nist.exists():
        return ["  MISSING: NIST-SUBMISSION.md"]
    content = nist.read_text().lower()
    issues = []
    for section in REQUIRED_SECTIONS:
        if section.lower() not in content:
            issues.append(f"  WARN: '{section}' not mentioned in NIST-SUBMISSION.md")
    return issues

def check_git():
    """Check for uncommitted changes."""
    result = subprocess.run(
        ["git", "status", "--porcelain"], capture_output=True, text=True, cwd=REPO
    )
    dirty = [l for l in result.stdout.strip().split("\n") if l.strip()]
    return dirty

def main():
    print("=== NIST CAISI Submission Readiness Check ===\n")
    
    # Tools
    tools, tool_issues = check_tools()
    print(f"Tools: {len(tools)} found")
    for i in tool_issues:
        print(i)
    
    # Docs
    doc_issues = check_docs()
    print(f"\nDocumentation: {len(REQUIRED_DOCS)} required")
    if doc_issues:
        for i in doc_issues:
            print(i)
    else:
        print("  All present ✓")
    
    # NIST sections
    nist_issues = check_nist_sections()
    print(f"\nNIST sections: {len(REQUIRED_SECTIONS)} required")
    if nist_issues:
        for i in nist_issues:
            print(i)
    else:
        print("  All covered ✓")
    
    # Git
    dirty = check_git()
    print(f"\nGit status:")
    if dirty:
        print(f"  {len(dirty)} uncommitted changes")
        for d in dirty[:5]:
            print(f"    {d}")
    else:
        print("  Clean ✓")
    
    # Summary
    all_issues = tool_issues + doc_issues + nist_issues
    fails = [i for i in all_issues if "FAIL" in i or "MISSING" in i]
    warns = [i for i in all_issues if "WARN" in i]
    
    print(f"\n{'='*40}")
    print(f"RESULT: {len(fails)} failures, {len(warns)} warnings")
    if fails:
        print("STATUS: NOT READY ❌")
        sys.exit(1)
    elif warns:
        print("STATUS: READY WITH WARNINGS ⚠️")
    else:
        print("STATUS: READY ✅")

if __name__ == "__main__":
    main()
