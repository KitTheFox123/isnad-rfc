#!/usr/bin/env python3
"""NIST CAISI Submission Review Checklist
Validates submission package completeness before March 9 deadline.
Checks: RFC structure, tool coverage, claims mapping, appendices.
"""

import os
import sys
import re
from pathlib import Path

REPO = Path(__file__).parent.parent
TOOLS_DIR = REPO / "tools"

REQUIRED_FILES = [
    "RFC.md",
    "README.md",
    "CONTRIBUTING.md",
    "APPENDIX-VERIFICATION-TIERS.md",
    "claims-mapping.md",
    "tools/NIST-SUBMISSION.md",
    "tools/PRE-MERGE-VALIDATION.md",
    "tools/README.md",
]

# RFC sections expected
RFC_SECTIONS = [
    "Abstract",
    "Introduction",
    "Terminology",
    "Trust Model",
    "Chain Structure",
    "Verification",
    "Security Considerations",
]

# Tools that should exist (core verification tools)
CORE_TOOLS = [
    "integer-brier-scorer.py",
    "collusion-detector.py",
    "commitment_verifier.py",
    "precommit-verifier.py",
    "event_scope_invalidator.py",
    "credible_commitment_analyzer.py",
    "procedure_commitment_auditor.py",
    "proximity_drift_scorer.py",
    "repetition_truth_detector.py",
    "attestation_loafing_detector.py",
]


def check_file_exists(path: str) -> tuple[bool, str]:
    full = REPO / path
    exists = full.exists()
    size = full.stat().st_size if exists else 0
    return exists, f"{'✅' if exists else '❌'} {path} ({size} bytes)" if exists else f"{'❌'} {path} (MISSING)"


def check_rfc_sections() -> list[str]:
    rfc = (REPO / "RFC.md").read_text()
    results = []
    for section in RFC_SECTIONS:
        found = section.lower() in rfc.lower()
        results.append(f"  {'✅' if found else '⚠️'} {section}")
    return results


def check_tools_have_docstrings() -> list[str]:
    results = []
    for tool in sorted(TOOLS_DIR.glob("*.py")):
        if tool.name == "nist-review-checklist.py":
            continue
        content = tool.read_text()
        has_doc = '"""' in content[:500] or "'''" in content[:500]
        results.append(f"  {'✅' if has_doc else '⚠️'} {tool.name} {'(has docstring)' if has_doc else '(NO docstring)'}")
    return results


def check_tool_tests() -> list[str]:
    """Check which tools have self-test / --test capability."""
    results = []
    for tool in CORE_TOOLS:
        path = TOOLS_DIR / tool
        if not path.exists():
            results.append(f"  ❌ {tool} (MISSING)")
            continue
        content = path.read_text()
        has_test = "--test" in content or "def test" in content or "assert " in content
        results.append(f"  {'✅' if has_test else '⚠️'} {tool} {'(has tests)' if has_test else '(no tests found)'}")
    return results


def main():
    print("=" * 60)
    print("NIST CAISI Submission Review Checklist")
    print(f"Repo: {REPO}")
    print("=" * 60)

    # 1. Required files
    print("\n📁 Required Files:")
    missing = 0
    for f in REQUIRED_FILES:
        exists, msg = check_file_exists(f)
        print(f"  {msg}")
        if not exists:
            missing += 1

    # 2. RFC sections
    print("\n📄 RFC Sections:")
    for line in check_rfc_sections():
        print(line)

    # 3. Core tools
    print("\n🔧 Core Tools:")
    for tool in CORE_TOOLS:
        path = TOOLS_DIR / tool
        exists = path.exists()
        print(f"  {'✅' if exists else '❌'} {tool}")

    # 4. Docstrings
    print("\n📝 Tool Docstrings:")
    for line in check_tools_have_docstrings():
        print(line)

    # 5. Tests
    print("\n🧪 Tool Tests:")
    for line in check_tool_tests():
        print(line)

    # 6. Git status
    print("\n🔀 Git Status:")
    branch = os.popen(f"cd {REPO} && git branch --show-current").read().strip()
    last_commit = os.popen(f"cd {REPO} && git log --oneline -1").read().strip()
    remote = os.popen(f"cd {REPO} && git remote -v | head -1").read().strip()
    print(f"  Branch: {branch}")
    print(f"  Last commit: {last_commit}")
    print(f"  Remote: {remote}")

    # Summary
    print("\n" + "=" * 60)
    total_tools = len(list(TOOLS_DIR.glob("*.py"))) - 1  # exclude self
    print(f"Summary: {len(REQUIRED_FILES) - missing}/{len(REQUIRED_FILES)} files, {total_tools} tools")
    if missing:
        print(f"⚠️  {missing} required file(s) missing!")
        sys.exit(1)
    else:
        print("✅ All required files present. Ready for review.")


if __name__ == "__main__":
    main()
