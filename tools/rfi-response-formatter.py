#!/usr/bin/env python3
"""
rfi-response-formatter.py — Format isnad-rfc tools + research into NIST CAISI RFI response.

NIST RFI on AI Agent Security asks about:
  1. Current threats and mitigations
  2. Measures for agent accountability
  3. Identity and authorization considerations

Maps our 34 tools to RFI themes and generates structured response.
"""

import os
import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone

TOOLS_DIR = Path(__file__).parent
REPO_ROOT = TOOLS_DIR.parent

# RFI themes from NIST CAISI (nist.gov/caisi/ai-agent-standards-initiative)
RFI_THEMES = {
    "threats": {
        "title": "Current Threats to AI Agent Systems",
        "description": "Threats including takeover, scope creep, collusion, silence-as-deception",
        "tools": [],
    },
    "mitigations": {
        "title": "Mitigations and Accountability Measures",
        "description": "Short-lived scope, attestation chains, transparency logs, dispute resolution",
        "tools": [],
    },
    "identity": {
        "title": "Identity and Authorization Infrastructure",
        "description": "Human root of trust, delegation chains, certificate transparency model",
        "tools": [],
    },
    "interop": {
        "title": "Interoperability and Protocol Considerations",
        "description": "Cross-platform attestation, format-agnostic provenance, MCP integration",
        "tools": [],
    },
}

# Tool-to-theme mapping
TOOL_THEMES = {
    "collusion-detector": ["threats"],
    "silence-detector": ["threats"],
    "selection-gap-detector": ["threats"],
    "human-root-audit": ["identity", "mitigations"],
    "scope-commit-at-issuance": ["identity", "mitigations"],
    "operationalized-intention": ["mitigations"],
    "scope-transparency-log": ["mitigations", "interop"],
    "attestation-burst-detector": ["threats"],
    "fork-fingerprint": ["mitigations", "interop"],
    "provenance-logger": ["mitigations", "interop"],
    "safety-liveness-classifier": ["mitigations"],
    "scope-vote-simulator": ["mitigations"],
    "dispute-oracle-sim": ["mitigations", "interop"],
    "nist-review-checklist": ["mitigations"],
    "submission-readiness": ["mitigations"],
    "nist-submission-readme": ["interop"],
    "stylometry": ["threats", "identity"],
    "metamemory-audit": ["mitigations"],
    "memory-compression-ratio": ["mitigations"],
}


def scan_tools():
    """Scan tools/ for Python files and extract docstrings."""
    tools = {}
    for f in sorted(TOOLS_DIR.glob("*.py")):
        if f.name == Path(__file__).name:
            continue
        name = f.stem
        content = f.read_text()
        # Extract first docstring
        doc = ""
        if '"""' in content:
            parts = content.split('"""')
            if len(parts) >= 3:
                doc = parts[1].strip()
        tools[name] = {
            "file": f.name,
            "docstring": doc[:200] if doc else "(no docstring)",
            "size": len(content),
            "hash": hashlib.sha256(content.encode()).hexdigest()[:12],
        }
    return tools


def classify_tools(tools):
    """Assign tools to RFI themes."""
    classified = {k: dict(v) for k, v in RFI_THEMES.items()}
    unclassified = []

    for name, info in tools.items():
        themes = TOOL_THEMES.get(name, [])
        if themes:
            for theme in themes:
                classified[theme]["tools"].append({"name": name, **info})
        else:
            unclassified.append({"name": name, **info})

    return classified, unclassified


def generate_response(classified, unclassified, tools):
    """Generate formatted RFI response."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        "# NIST CAISI RFI Response: AI Agent Security",
        f"# Generated: {now}",
        f"# Source: isnad-rfc (github.com/KitTheFox123/isnad-rfc)",
        f"# Tools analyzed: {len(tools)}",
        "",
        "## Executive Summary",
        "",
        "We present isnad-rfc, a framework for agent accountability inspired by",
        "hadith science's isnad (chain of transmission) methodology. The framework",
        "provides 34 open-source tools addressing four key areas of the NIST CAISI",
        "RFI: threat detection, accountability mitigations, identity infrastructure,",
        "and interoperability protocols.",
        "",
        "### Core Thesis",
        "",
        "Agent accountability requires the same infrastructure as certificate",
        "transparency: append-only logs, short-lived scope commitments, public",
        "monitors, and a human root of trust. Every autonomous agent must trace",
        "its authority to a human principal through a verifiable delegation chain.",
        "",
        "---",
        "",
    ]

    for theme_id, theme in classified.items():
        lines.append(f"## {theme['title']}")
        lines.append("")
        lines.append(f"*{theme['description']}*")
        lines.append("")

        if theme["tools"]:
            lines.append(f"### Tools ({len(theme['tools'])})")
            lines.append("")
            for t in theme["tools"]:
                doc_line = t["docstring"].split("\n")[0] if t["docstring"] else ""
                lines.append(f"- **{t['name']}** (`{t['file']}`, sha256:{t['hash']})")
                if doc_line and doc_line != "(no docstring)":
                    lines.append(f"  {doc_line}")
            lines.append("")
        else:
            lines.append("*(no tools directly mapped)*")
            lines.append("")

    if unclassified:
        lines.append("## Additional Tools (Supporting)")
        lines.append("")
        for t in unclassified:
            lines.append(f"- **{t['name']}** (`{t['file']}`)")
        lines.append("")

    lines.extend([
        "---",
        "",
        "## Key References",
        "",
        "- humanrootoftrust.org — Public-domain framework for human terminus",
        "- RFC 9162 — Certificate Transparency Version 2.0",
        "- Russ Cox, 'Transparent Logs for Skeptical Clients' (2019)",
        "- Gollwitzer (1999) — Implementation intentions",
        "- Baron & Ritov (1991) — Omission bias",
        "- Kalyuga (2007) — Expertise reversal effect",
        "",
        "## Submission Metadata",
        "",
        f"- Repository: https://github.com/KitTheFox123/isnad-rfc",
        f"- Contact: kit_fox@agentmail.to",
        f"- Generated: {now}",
        f"- Tool count: {len(tools)}",
        f"- Deadline: March 9, 2026",
    ])

    return "\n".join(lines)


def main():
    tools = scan_tools()
    classified, unclassified = classify_tools(tools)

    print(f"=== NIST CAISI RFI Response Formatter ===\n")
    print(f"Tools scanned: {len(tools)}")

    for theme_id, theme in classified.items():
        print(f"  {theme['title']}: {len(theme['tools'])} tools")

    print(f"  Unclassified: {len(unclassified)}")
    print()

    response = generate_response(classified, unclassified, tools)

    output_path = REPO_ROOT / "NIST-RFI-RESPONSE.md"
    output_path.write_text(response)
    print(f"Written to: {output_path}")
    print(f"Size: {len(response)} bytes")

    # Also output JSON manifest
    manifest = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "tool_count": len(tools),
        "themes": {k: len(v["tools"]) for k, v in classified.items()},
        "unclassified": len(unclassified),
        "tools": {name: info["hash"] for name, info in tools.items()},
    }
    manifest_path = REPO_ROOT / "nist-rfi-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
