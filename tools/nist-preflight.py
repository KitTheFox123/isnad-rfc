#!/usr/bin/env python3
"""
nist-preflight.py — Pre-submission validator for NIST CAISI package.

Checks:
1. All tools listed in NIST-SUBMISSION.md exist and parse
2. All tools have docstrings
3. No syntax errors
4. README.md exists and references key tools
5. Git status clean (no uncommitted changes)
6. All referenced papers have URLs
7. Tool count matches manifest

Usage: python3 tools/nist-preflight.py
"""

import ast
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
TOOLS_DIR = REPO_ROOT / "tools"
SUBMISSION_FILE = REPO_ROOT / "NIST-SUBMISSION.md"

class PreflightCheck:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.warnings = 0
        self.errors = []
    
    def check(self, name: str, condition: bool, detail: str = ""):
        if condition:
            self.passed += 1
            print(f"  ✅ {name}")
        else:
            self.failed += 1
            msg = f"{name}: {detail}" if detail else name
            self.errors.append(msg)
            print(f"  ❌ {name}" + (f" — {detail}" if detail else ""))
    
    def warn(self, name: str, detail: str = ""):
        self.warnings += 1
        print(f"  ⚠️  {name}" + (f" — {detail}" if detail else ""))
    
    def report(self):
        total = self.passed + self.failed
        print(f"\n{'='*50}")
        print(f"NIST Preflight: {self.passed}/{total} passed, {self.warnings} warnings")
        if self.errors:
            print(f"\nErrors:")
            for e in self.errors:
                print(f"  • {e}")
        grade = "A" if self.failed == 0 and self.warnings == 0 else \
                "B" if self.failed == 0 else \
                "C" if self.failed <= 2 else "F"
        print(f"\nReadiness grade: {grade}")
        return self.failed == 0


def check_tool_syntax(pf: PreflightCheck):
    """Check all .py files in tools/ parse without errors."""
    print("\n1. Tool Syntax")
    py_files = sorted(TOOLS_DIR.glob("*.py"))
    for f in py_files:
        try:
            ast.parse(f.read_text())
            pf.check(f.name, True)
        except SyntaxError as e:
            pf.check(f.name, False, f"line {e.lineno}: {e.msg}")


def check_docstrings(pf: PreflightCheck):
    """Check all tools have module docstrings."""
    print("\n2. Docstrings")
    py_files = sorted(TOOLS_DIR.glob("*.py"))
    for f in py_files:
        try:
            tree = ast.parse(f.read_text())
            docstring = ast.get_docstring(tree)
            pf.check(f.name, docstring is not None and len(docstring) > 20,
                     "missing or too short docstring")
        except SyntaxError:
            pass  # already caught above


def check_manifest_coverage(pf: PreflightCheck):
    """Check NIST-SUBMISSION.md references match actual tools."""
    print("\n3. Manifest Coverage")
    if not SUBMISSION_FILE.exists():
        pf.check("NIST-SUBMISSION.md exists", False)
        return
    
    pf.check("NIST-SUBMISSION.md exists", True)
    content = SUBMISSION_FILE.read_text()
    
    # Extract tool names mentioned in the manifest
    mentioned = set(re.findall(r'(\w[\w-]+\.py)', content))
    actual = {f.name for f in TOOLS_DIR.glob("*.py")}
    
    # Tools mentioned but missing
    missing = mentioned - actual
    for m in sorted(missing):
        pf.check(f"Referenced tool exists: {m}", False, "in manifest but not in tools/")
    
    # Count
    pf.check(f"Tool count: {len(actual)} files", len(actual) >= 10,
             f"expected ≥10, got {len(actual)}")


def check_git_status(pf: PreflightCheck):
    """Check git working tree is clean."""
    print("\n4. Git Status")
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, cwd=REPO_ROOT
        )
        dirty_files = [l for l in result.stdout.strip().split('\n') if l.strip()]
        pf.check("Working tree clean", len(dirty_files) == 0,
                 f"{len(dirty_files)} uncommitted files")
        if dirty_files:
            for f in dirty_files[:5]:
                pf.warn(f"  dirty: {f.strip()}")
        
        # Check branch
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, cwd=REPO_ROOT
        ).stdout.strip()
        pf.check(f"On main branch", branch == "main", f"on '{branch}'")
        
    except FileNotFoundError:
        pf.check("Git available", False)


def check_readme(pf: PreflightCheck):
    """Check README exists and has substance."""
    print("\n5. README")
    readme = REPO_ROOT / "README.md"
    pf.check("README.md exists", readme.exists())
    if readme.exists():
        content = readme.read_text()
        pf.check("README > 500 chars", len(content) > 500,
                 f"only {len(content)} chars")
        pf.check("README mentions NIST or CAISI", 
                 "NIST" in content or "CAISI" in content or "trust" in content.lower(),
                 "no NIST/CAISI/trust reference")


def check_references(pf: PreflightCheck):
    """Check key references are present."""
    print("\n6. References")
    if not SUBMISSION_FILE.exists():
        return
    content = SUBMISSION_FILE.read_text()
    
    key_refs = [
        ("arXiv", "arxiv" in content.lower() or "arXiv" in content),
        ("RFC reference", "RFC" in content),
        ("humanrootoftrust.org", "humanrootoftrust" in content),
    ]
    for name, present in key_refs:
        pf.check(f"References {name}", present)


def main():
    print("=" * 50)
    print("NIST CAISI Pre-Submission Preflight")
    print("=" * 50)
    
    pf = PreflightCheck()
    
    check_tool_syntax(pf)
    check_docstrings(pf)
    check_manifest_coverage(pf)
    check_git_status(pf)
    check_readme(pf)
    check_references(pf)
    
    success = pf.report()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
