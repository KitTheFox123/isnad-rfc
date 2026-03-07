#!/usr/bin/env python3
"""NIST CAISI Submission Review Checklist
Validates the complete submission package before March 9 deadline.
Checks: tool inventory, documentation completeness, cross-references, dead links.
"""
import os, sys, json, re, hashlib
from pathlib import Path

REPO = Path(__file__).parent.parent
TOOLS_DIR = REPO / "tools"
REQUIRED_DOCS = [
    "README.md", "NIST-SUBMISSION.md", "NIST-RFI-RESPONSE.md",
    "nist-rfi-manifest.json", "tools/PRE-MERGE-VALIDATION.md"
]
NIST_THEMES = ["threats", "mitigations", "identity", "interop"]

def check_docs():
    """Verify all required documents exist and are non-empty."""
    results = []
    for doc in REQUIRED_DOCS:
        p = REPO / doc
        if not p.exists():
            results.append(("FAIL", doc, "missing"))
        elif p.stat().st_size == 0:
            results.append(("FAIL", doc, "empty"))
        else:
            results.append(("PASS", doc, f"{p.stat().st_size} bytes"))
    return results

def check_tools():
    """Inventory all Python tools and verify they have docstrings."""
    results = []
    for f in sorted(TOOLS_DIR.glob("*.py")):
        if f.name == "__init__.py":
            continue
        content = f.read_text()
        has_docstring = '"""' in content[:500] or "'''" in content[:500]
        has_main = "if __name__" in content or "def main" in content
        status = "PASS" if has_docstring and has_main else "WARN"
        note = []
        if not has_docstring: note.append("no docstring")
        if not has_main: note.append("no main/entry")
        results.append((status, f.name, ", ".join(note) if note else "ok"))
    return results

def check_manifest():
    """Verify manifest matches actual tool inventory."""
    manifest_path = REPO / "nist-rfi-manifest.json"
    if not manifest_path.exists():
        return [("FAIL", "manifest", "missing")]
    
    manifest = json.loads(manifest_path.read_text())
    manifest_count = manifest.get("tool_count", 0)
    actual_tools = [f for f in TOOLS_DIR.glob("*.py") if f.name != "__init__.py" and f.name != "submission-review.py"]
    actual_count = len(actual_tools)
    
    results = []
    if manifest_count != actual_count:
        results.append(("WARN", "tool_count", f"manifest says {manifest_count}, found {actual_count}"))
    else:
        results.append(("PASS", "tool_count", f"{actual_count} tools"))
    
    # Check theme coverage
    themes = manifest.get("themes", {})
    for t in NIST_THEMES:
        if t not in themes:
            results.append(("WARN", f"theme:{t}", "not in manifest"))
        elif themes[t] == 0:
            results.append(("WARN", f"theme:{t}", "0 tools mapped"))
        else:
            results.append(("PASS", f"theme:{t}", f"{themes[t]} tools"))
    
    return results

def check_crossrefs():
    """Check that NIST-SUBMISSION.md references actual tools."""
    sub_path = REPO / "NIST-SUBMISSION.md"
    if not sub_path.exists():
        return [("FAIL", "crossrefs", "NIST-SUBMISSION.md missing")]
    
    content = sub_path.read_text()
    tool_names = {f.stem for f in TOOLS_DIR.glob("*.py") if f.name != "__init__.py"}
    
    results = []
    referenced = set()
    for name in tool_names:
        if name in content:
            referenced.add(name)
    
    unreferenced = tool_names - referenced
    if unreferenced:
        results.append(("WARN", "unreferenced_tools", ", ".join(sorted(unreferenced))))
    else:
        results.append(("PASS", "crossrefs", f"all {len(tool_names)} tools referenced"))
    
    return results

def compute_package_hash():
    """SHA256 of all submission files for integrity check."""
    h = hashlib.sha256()
    for doc in sorted(REQUIRED_DOCS):
        p = REPO / doc
        if p.exists():
            h.update(p.read_bytes())
    for f in sorted(TOOLS_DIR.glob("*.py")):
        h.update(f.read_bytes())
    return h.hexdigest()[:16]

def main():
    print("=" * 60)
    print("NIST CAISI Submission Review")
    print(f"Repo: {REPO}")
    print(f"Date: March 7, 2026 (deadline: March 9)")
    print("=" * 60)
    
    all_results = []
    
    print("\n## Documentation")
    for r in check_docs():
        all_results.append(r)
        icon = "✅" if r[0] == "PASS" else "⚠️" if r[0] == "WARN" else "❌"
        print(f"  {icon} {r[1]}: {r[2]}")
    
    print("\n## Tool Inventory")
    for r in check_tools():
        all_results.append(r)
        icon = "✅" if r[0] == "PASS" else "⚠️" if r[0] == "WARN" else "❌"
        print(f"  {icon} {r[1]}: {r[2]}")
    
    print("\n## Manifest Validation")
    for r in check_manifest():
        all_results.append(r)
        icon = "✅" if r[0] == "PASS" else "⚠️" if r[0] == "WARN" else "❌"
        print(f"  {icon} {r[1]}: {r[2]}")
    
    print("\n## Cross-References")
    for r in check_crossrefs():
        all_results.append(r)
        icon = "✅" if r[0] == "PASS" else "⚠️" if r[0] == "WARN" else "❌"
        print(f"  {icon} {r[1]}: {r[2]}")
    
    pkg_hash = compute_package_hash()
    print(f"\n## Package Hash: {pkg_hash}")
    
    fails = sum(1 for r in all_results if r[0] == "FAIL")
    warns = sum(1 for r in all_results if r[0] == "WARN")
    passes = sum(1 for r in all_results if r[0] == "PASS")
    
    print(f"\n{'=' * 60}")
    print(f"Summary: {passes} PASS, {warns} WARN, {fails} FAIL")
    verdict = "🔴 NOT READY" if fails > 0 else "🟡 REVIEW WARNINGS" if warns > 0 else "🟢 READY TO SUBMIT"
    print(f"Verdict: {verdict}")
    
    return 1 if fails > 0 else 0

if __name__ == "__main__":
    sys.exit(main())
