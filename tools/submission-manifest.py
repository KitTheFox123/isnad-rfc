#!/usr/bin/env python3
"""Generate NIST CAISI submission manifest with integrity hashes."""
import hashlib, json, os, sys
from datetime import datetime, timezone
from pathlib import Path

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()

def main():
    repo = Path(__file__).parent.parent
    manifest = {
        "submission": "isnad-rfc",
        "target": "NIST CAISI",
        "deadline": "2026-03-09",
        "generated": datetime.now(timezone.utc).isoformat(),
        "files": [],
        "tools_count": 0,
        "integrity": {}
    }
    
    # Core documents
    core_files = ["NIST-SUBMISSION.md", "RFC.md", "README.md", "LICENSE"]
    for f in core_files:
        p = repo / f
        if p.exists():
            manifest["files"].append({
                "path": f,
                "sha256": sha256_file(p),
                "size": p.stat().st_size
            })
    
    # Tools
    tools_dir = repo / "tools"
    tool_files = sorted(tools_dir.glob("*.py"))
    manifest["tools_count"] = len(tool_files)
    
    tool_hashes = {}
    for t in tool_files:
        h = sha256_file(t)
        tool_hashes[t.name] = h
        manifest["files"].append({
            "path": f"tools/{t.name}",
            "sha256": h,
            "size": t.stat().st_size
        })
    
    # Merkle root of all tool hashes (sorted)
    combined = "".join(tool_hashes[k] for k in sorted(tool_hashes))
    manifest["integrity"]["tools_merkle_root"] = hashlib.sha256(combined.encode()).hexdigest()
    manifest["integrity"]["total_files"] = len(manifest["files"])
    
    out = repo / "SUBMISSION-MANIFEST.json"
    with open(out, 'w') as f:
        json.dump(manifest, f, indent=2)
    
    print(f"Manifest: {len(manifest['files'])} files, {manifest['tools_count']} tools")
    print(f"Merkle root: {manifest['integrity']['tools_merkle_root'][:16]}...")
    print(f"Written to {out}")

if __name__ == "__main__":
    main()
