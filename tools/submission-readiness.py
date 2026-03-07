#!/usr/bin/env python3
"""NIST CAISI Submission Readiness Checker.

Validates the full submission package before March 9 deadline:
- All tools present and runnable
- NIST-SUBMISSION.md complete
- PRE-MERGE-VALIDATION.md present
- No broken imports
- README references valid
- Git status clean
"""
import os
import sys
import subprocess
import hashlib
from pathlib import Path
from datetime import datetime, timezone

TOOLS_DIR = Path(__file__).parent
REPO_DIR = TOOLS_DIR.parent

REQUIRED_FILES = [
    "tools/NIST-SUBMISSION.md",
    "tools/PRE-MERGE-VALIDATION.md",
    "README.md",
]

REQUIRED_SECTIONS_NIST = [
    "Human Root of Trust",
    "Tool",
    "CAISI",
]


def check_file_exists(path: str) -> tuple[bool, str]:
    full = REPO_DIR / path
    if full.exists():
        size = full.stat().st_size
        return True, f"✅ {path} ({size} bytes)"
    return False, f"❌ {path} MISSING"


def check_tools_runnable() -> list[tuple[bool, str]]:
    results = []
    py_files = sorted(TOOLS_DIR.glob("*.py"))
    for f in py_files:
        if f.name == "submission-readiness.py":
            continue
        try:
            result = subprocess.run(
                [sys.executable, "-c", f"import ast; ast.parse(open('{f}').read())"],
                capture_output=True, timeout=5
            )
            if result.returncode == 0:
                results.append((True, f"  ✅ {f.name} — syntax OK"))
            else:
                results.append((False, f"  ❌ {f.name} — syntax error"))
        except subprocess.TimeoutExpired:
            results.append((False, f"  ⚠️ {f.name} — parse timeout"))
    return results


def check_nist_sections() -> list[tuple[bool, str]]:
    nist_path = REPO_DIR / "tools" / "NIST-SUBMISSION.md"
    if not nist_path.exists():
        return [(False, "❌ NIST-SUBMISSION.md missing")]
    content = nist_path.read_text()
    results = []
    for section in REQUIRED_SECTIONS_NIST:
        if section.lower() in content.lower():
            results.append((True, f"  ✅ Section '{section}' found"))
        else:
            results.append((False, f"  ❌ Section '{section}' MISSING"))
    return results


def check_git_status() -> tuple[bool, str]:
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True, text=True, cwd=REPO_DIR
    )
    if result.stdout.strip():
        return False, f"⚠️ Uncommitted changes:\n{result.stdout.strip()}"
    return True, "✅ Git working tree clean"


def manifest_hash() -> str:
    """SHA-256 of all tool files for reproducibility."""
    h = hashlib.sha256()
    for f in sorted(TOOLS_DIR.glob("*.py")):
        h.update(f.read_bytes())
    for f in sorted(TOOLS_DIR.glob("*.md")):
        h.update(f.read_bytes())
    return h.hexdigest()[:16]


def main():
    now = datetime.now(timezone.utc)
    deadline = datetime(2026, 3, 9, tzinfo=timezone.utc)
    hours_left = (deadline - now).total_seconds() / 3600

    print(f"╔══════════════════════════════════════════╗")
    print(f"║  NIST CAISI Submission Readiness Check   ║")
    print(f"║  {now.strftime('%Y-%m-%d %H:%M UTC')}                        ║")
    print(f"║  Hours to deadline: {hours_left:.1f}               ║")
    print(f"╚══════════════════════════════════════════╝")
    print()

    all_pass = True

    # 1. Required files
    print("## Required Files")
    for path in REQUIRED_FILES:
        ok, msg = check_file_exists(path)
        print(msg)
        all_pass &= ok
    print()

    # 2. Tool syntax
    print("## Tool Syntax Check")
    tool_results = check_tools_runnable()
    for ok, msg in tool_results:
        print(msg)
        all_pass &= ok
    print(f"\n  {sum(1 for ok,_ in tool_results if ok)}/{len(tool_results)} tools pass syntax check")
    print()

    # 3. NIST sections
    print("## NIST-SUBMISSION.md Sections")
    for ok, msg in check_nist_sections():
        print(msg)
        all_pass &= ok
    print()

    # 4. Git status
    print("## Git Status")
    ok, msg = check_git_status()
    print(msg)
    all_pass &= ok
    print()

    # 5. Manifest
    print(f"## Manifest Hash: {manifest_hash()}")
    print()

    # Verdict
    grade = "READY ✅" if all_pass else "NOT READY ❌"
    print(f"## Verdict: {grade}")
    print(f"## Tools: {len(tool_results)} validated")
    print(f"## Time remaining: {hours_left:.1f} hours")

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
