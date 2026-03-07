#!/usr/bin/env python3
"""Generate a human-readable README for NIST CAISI submission.

Scans all tools in the tools/ directory, extracts docstrings and key
metadata, and produces a formatted README suitable for reviewers.
"""
import ast
import os
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).parent

def extract_tool_info(filepath: Path) -> dict:
    """Extract docstring and key info from a tool file."""
    source = filepath.read_text()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {"name": filepath.stem, "docstring": "(parse error)", "lines": 0}
    
    docstring = ast.get_docstring(tree) or "(no docstring)"
    lines = len(source.splitlines())
    
    # Check for main function
    has_main = any(
        isinstance(node, ast.FunctionDef) and node.name == "main"
        for node in ast.walk(tree)
    )
    
    # Count imports
    imports = sum(1 for node in ast.walk(tree) 
                  if isinstance(node, (ast.Import, ast.ImportFrom)))
    
    return {
        "name": filepath.stem,
        "docstring": docstring,
        "lines": lines,
        "has_main": has_main,
        "imports": imports,
    }

def main():
    tools = sorted(TOOLS_DIR.glob("*.py"))
    tools = [t for t in tools if t.name != "nist-submission-readme.py" and t.name != "__init__.py"]
    
    print("# isnad-rfc Tools — NIST CAISI Submission")
    print()
    print(f"**Tool count:** {len(tools)}")
    print(f"**Total lines:** {sum(len(t.read_text().splitlines()) for t in tools)}")
    print()
    print("## Overview")
    print()
    print("These tools operationalize the isnad-rfc framework for agent")
    print("delegation chains. Each tool addresses a specific accountability")
    print("primitive: scope verification, trust chain validation, collusion")
    print("detection, and human root-of-trust auditing.")
    print()
    print("## Tools")
    print()
    
    for tool_path in tools:
        info = extract_tool_info(tool_path)
        first_line = info["docstring"].split("\n")[0]
        print(f"### `{info['name']}.py`")
        print()
        print(f"**Purpose:** {first_line}")
        print(f"**Lines:** {info['lines']} | **Imports:** {info['imports']}")
        print()
        # Print full docstring if multi-line
        if "\n" in info["docstring"]:
            for line in info["docstring"].split("\n")[1:]:
                if line.strip():
                    print(f"> {line.strip()}")
            print()
        print("---")
        print()
    
    print("## Quick Start")
    print()
    print("```bash")
    print("# Run all tool self-tests")
    print("for f in tools/*.py; do python3 \"$f\" --help 2>/dev/null || echo \"$f: no --help\"; done")
    print()
    print("# Validate submission package")
    print("python3 tools/pre-submit-validator.py")
    print("```")
    print()
    print("## Framework")
    print()
    print("See `NIST-SUBMISSION.md` for the full submission narrative,")
    print("including alignment with the Human Root of Trust framework")
    print("(humanrootoftrust.org, Feb 2026).")

if __name__ == "__main__":
    main()
