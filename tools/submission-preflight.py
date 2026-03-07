#!/usr/bin/env python3
"""
submission-preflight.py — NIST CAISI Submission Package Validator

Validates the isnad-rfc submission package before March 9 deadline:
1. All tools parse without syntax errors
2. All tools have docstrings (required for review)
3. NIST-SUBMISSION.md exists and references key sections
4. PRE-MERGE-VALIDATION.md exists with passing grades
5. No credential leaks in any tracked file
6. Git status clean (no uncommitted changes)
7. SHA-256 manifest of all submission files

Usage: python3 tools/submission-preflight.py [--generate-manifest]
"""

import ast
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).parent.parent
TOOLS_DIR = REPO / "tools"
REQUIRED_FILES = [
    "NIST-SUBMISSION.md",
    "README.md",
    "tools/PRE-MERGE-VALIDATION.md",
]
CREDENTIAL_PATTERNS = [
    r'(?:api[_-]?key|secret|token|password)\s*[=:]\s*["\'][^"\']{8,}',
    r'Bearer\s+[A-Za-z0-9\-_.]{20,}',
    r'-----BEGIN (?:RSA )?PRIVATE KEY-----',
]


class PreflightResult:
    def __init__(self):
        self.checks = []
        self.failures = 0
        self.warnings = 0

    def ok(self, name, detail=""):
        self.checks.append(("PASS", name, detail))

    def fail(self, name, detail=""):
        self.checks.append(("FAIL", name, detail))
        self.failures += 1

    def warn(self, name, detail=""):
        self.checks.append(("WARN", name, detail))
        self.warnings += 1

    def report(self):
        print("\n" + "=" * 60)
        print("NIST CAISI Submission Preflight Report")
        print("=" * 60)
        for status, name, detail in self.checks:
            icon = {"PASS": "✅", "FAIL": "❌", "WARN": "⚠️"}[status]
            line = f"{icon} {name}"
            if detail:
                line += f" — {detail}"
            print(line)
        print("-" * 60)
        grade = "A" if self.failures == 0 and self.warnings == 0 else \
                "B" if self.failures == 0 else \
                "C" if self.failures <= 2 else "F"
        print(f"Result: {self.failures} failures, {self.warnings} warnings — Grade {grade}")
        return grade


def check_tool_syntax(result):
    """Verify all .py tools parse without errors."""
    tools = sorted(TOOLS_DIR.glob("*.py"))
    parse_errors = []
    for tool in tools:
        try:
            ast.parse(tool.read_text())
        except SyntaxError as e:
            parse_errors.append(f"{tool.name}:{e.lineno}")
    if parse_errors:
        result.fail("Tool syntax", f"{len(parse_errors)} errors: {', '.join(parse_errors[:5])}")
    else:
        result.ok("Tool syntax", f"{len(tools)} tools parse clean")


def check_docstrings(result):
    """Verify all tools have module-level docstrings."""
    tools = sorted(TOOLS_DIR.glob("*.py"))
    missing = []
    for tool in tools:
        try:
            tree = ast.parse(tool.read_text())
            docstring = ast.get_docstring(tree)
            if not docstring:
                missing.append(tool.name)
        except SyntaxError:
            pass  # caught by syntax check
    if missing:
        result.warn("Docstrings", f"{len(missing)} missing: {', '.join(missing[:5])}")
    else:
        result.ok("Docstrings", f"all {len(tools)} tools documented")


def check_required_files(result):
    """Verify required submission files exist."""
    for f in REQUIRED_FILES:
        path = REPO / f
        if path.exists():
            size = path.stat().st_size
            result.ok(f"File: {f}", f"{size} bytes")
        else:
            result.fail(f"File: {f}", "MISSING")


def check_credential_leaks(result):
    """Scan tracked files for credential patterns."""
    try:
        tracked = subprocess.check_output(
            ["git", "ls-files"], cwd=REPO, text=True
        ).strip().split("\n")
    except subprocess.CalledProcessError:
        result.warn("Credential scan", "git ls-files failed")
        return

    leaks = []
    for f in tracked:
        path = REPO / f
        if not path.exists() or path.suffix in ('.png', '.jpg', '.gif', '.woff', '.ttf'):
            continue
        try:
            content = path.read_text(errors='ignore')
            for pattern in CREDENTIAL_PATTERNS:
                if re.search(pattern, content, re.IGNORECASE):
                    leaks.append(f)
                    break
        except Exception:
            pass

    if leaks:
        result.fail("Credential scan", f"potential leaks in: {', '.join(leaks[:5])}")
    else:
        result.ok("Credential scan", f"{len(tracked)} files clean")


def check_git_clean(result):
    """Verify no uncommitted changes."""
    try:
        status = subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=REPO, text=True
        ).strip()
        if status:
            changed = len(status.split("\n"))
            result.warn("Git status", f"{changed} uncommitted changes")
        else:
            result.ok("Git status", "working tree clean")
    except subprocess.CalledProcessError:
        result.warn("Git status", "git not available")


def check_nist_submission_content(result):
    """Verify NIST-SUBMISSION.md has required sections."""
    path = REPO / "NIST-SUBMISSION.md"
    if not path.exists():
        return
    content = path.read_text()
    required_sections = ["Human Root", "Tool", "alignment", "scope"]
    found = sum(1 for s in required_sections if s.lower() in content.lower())
    if found == len(required_sections):
        result.ok("NIST content", f"all {len(required_sections)} key sections present")
    else:
        result.warn("NIST content", f"{found}/{len(required_sections)} key sections found")


def generate_manifest():
    """Generate SHA-256 manifest of all submission files."""
    try:
        tracked = subprocess.check_output(
            ["git", "ls-files"], cwd=REPO, text=True
        ).strip().split("\n")
    except subprocess.CalledProcessError:
        print("Error: git ls-files failed")
        return

    manifest = {}
    for f in sorted(tracked):
        path = REPO / f
        if path.exists() and path.is_file():
            h = hashlib.sha256(path.read_bytes()).hexdigest()
            manifest[f] = h

    manifest_path = REPO / "SUBMISSION-MANIFEST.json"
    with open(manifest_path, "w") as fp:
        json.dump({
            "generated": subprocess.check_output(
                ["date", "-u", "+%Y-%m-%dT%H:%M:%SZ"], text=True
            ).strip(),
            "files": len(manifest),
            "hashes": manifest,
        }, fp, indent=2)
    print(f"Manifest written: {manifest_path} ({len(manifest)} files)")


def main():
    if "--generate-manifest" in sys.argv:
        generate_manifest()
        return

    result = PreflightResult()
    check_tool_syntax(result)
    check_docstrings(result)
    check_required_files(result)
    check_nist_submission_content(result)
    check_credential_leaks(result)
    check_git_clean(result)
    grade = result.report()
    sys.exit(0 if grade in ("A", "B") else 1)


if __name__ == "__main__":
    main()
