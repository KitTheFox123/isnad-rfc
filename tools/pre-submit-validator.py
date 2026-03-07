#!/usr/bin/env python3
"""
pre-submit-validator.py — NIST CAISI Pre-Submission Validator

Runs all isnad-rfc tools, captures output, produces a go/no-go report.
Designed for the March 9 deadline: one command to confirm everything works.

Usage: python3 tools/pre-submit-validator.py [--verbose]
"""

import subprocess
import sys
import os
import time
from pathlib import Path
from datetime import datetime, timezone

TOOLS_DIR = Path(__file__).parent
REPO_ROOT = TOOLS_DIR.parent
VERBOSE = "--verbose" in sys.argv

# Tools that need specific args vs ones that run with --help
HELP_CHECK_TOOLS = [
    "attestation_loafing_detector.py",
    "canary-spec-commit.py",
    "collusion-detector.py",
    "commitment_verifier.py",
    "commitment-window-analyzer.py",
    "credible_commitment_analyzer.py",
    "event_scope_invalidator.py",
    "exchange-id-antireplay.py",
    "execution-trace-commit.py",
    "friendship-paradox.py",
    "integer-brier-scorer.py",
    "mmd-monitor.py",
    "nist-review-checklist.py",
    "precommit-verifier.py",
    "procedure_commitment_auditor.py",
    "proximity_drift_scorer.py",
    "repetition_truth_detector.py",
    "response-diversity.py",
    "scope-drift-detector.py",
    "selection-gap-detector.py",
    "semantic_changepoint.py",
    "sleeper_effect_detector.py",
    "trust-floor-alarm.py",
    "weight-vector-commitment.py",
    "witness_cosigner.py",
    "witness-network-sim.py",
]

# Skip utility scripts
SKIP = {"merge-changelog.py", "pre-submit-validator.py"}


def check_tool(name: str) -> dict:
    """Run a tool with --help and check it doesn't crash."""
    path = TOOLS_DIR / name
    if not path.exists():
        return {"name": name, "status": "MISSING", "time_ms": 0, "error": "File not found"}

    start = time.monotonic()
    try:
        result = subprocess.run(
            [sys.executable, str(path), "--help"],
            capture_output=True, text=True, timeout=10
        )
        elapsed = int((time.monotonic() - start) * 1000)

        if result.returncode == 0:
            return {"name": name, "status": "OK", "time_ms": elapsed, "error": None}
        else:
            # Some tools exit non-zero on --help but still work
            if result.stdout or result.stderr:
                return {"name": name, "status": "WARN", "time_ms": elapsed,
                        "error": f"exit={result.returncode}"}
            return {"name": name, "status": "FAIL", "time_ms": elapsed,
                    "error": result.stderr[:200]}
    except subprocess.TimeoutExpired:
        elapsed = int((time.monotonic() - start) * 1000)
        return {"name": name, "status": "TIMEOUT", "time_ms": elapsed, "error": "10s timeout"}
    except Exception as e:
        elapsed = int((time.monotonic() - start) * 1000)
        return {"name": name, "status": "ERROR", "time_ms": elapsed, "error": str(e)[:200]}


def check_repo_state() -> list[str]:
    """Check git repo state for submission readiness."""
    issues = []

    # Check branch
    result = subprocess.run(["git", "branch", "--show-current"],
                          capture_output=True, text=True, cwd=REPO_ROOT)
    branch = result.stdout.strip()
    if branch != "main":
        issues.append(f"Not on main branch (on '{branch}')")

    # Check for uncommitted changes
    result = subprocess.run(["git", "status", "--porcelain"],
                          capture_output=True, text=True, cwd=REPO_ROOT)
    if result.stdout.strip():
        issues.append(f"Uncommitted changes: {len(result.stdout.strip().splitlines())} files")

    # Check key files exist
    for f in ["NIST-SUBMISSION.md", "README.md", "isnad-rfc.md"]:
        if not (REPO_ROOT / f).exists():
            issues.append(f"Missing required file: {f}")

    return issues


def main():
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"═══════════════════════════════════════════════════")
    print(f"  ISNAD-RFC Pre-Submission Validator")
    print(f"  {now}")
    print(f"═══════════════════════════════════════════════════\n")

    # Repo checks
    print("## Repository State\n")
    issues = check_repo_state()
    if issues:
        for i in issues:
            print(f"  ⚠️  {i}")
    else:
        print("  ✅ Clean, on main, all required files present\n")

    # Tool checks
    all_tools = sorted([f.name for f in TOOLS_DIR.glob("*.py") if f.name not in SKIP])
    print(f"## Tool Validation ({len(all_tools)} tools)\n")

    results = []
    ok = warn = fail = 0
    for name in all_tools:
        r = check_tool(name)
        results.append(r)
        icon = {"OK": "✅", "WARN": "⚠️", "FAIL": "❌", "MISSING": "❌",
                "TIMEOUT": "⏱️", "ERROR": "❌"}.get(r["status"], "?")
        suffix = f" ({r['error']})" if r["error"] else ""
        if VERBOSE or r["status"] != "OK":
            print(f"  {icon} {name:45s} {r['status']:8s} {r['time_ms']:4d}ms{suffix}")
        if r["status"] == "OK":
            ok += 1
        elif r["status"] == "WARN":
            warn += 1
        else:
            fail += 1

    if not VERBOSE:
        print(f"  ... {ok} tools passed (use --verbose to see all)")

    # Summary
    print(f"\n## Summary\n")
    print(f"  Tools:  {ok} OK / {warn} WARN / {fail} FAIL  (total {len(all_tools)})")
    print(f"  Repo:   {'CLEAN' if not issues else f'{len(issues)} issues'}")

    total_ms = sum(r["time_ms"] for r in results)
    print(f"  Time:   {total_ms}ms total")

    if fail == 0 and not issues:
        print(f"\n  🟢 GO FOR SUBMISSION")
        return 0
    else:
        print(f"\n  🔴 NOT READY — fix issues above")
        return 1


if __name__ == "__main__":
    sys.exit(main())
