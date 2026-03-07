#!/usr/bin/env python3
"""
mmd-monitor.py — Maximum Merge Delay monitor for agent heartbeats.

Inspired by Certificate Transparency's MMD concept (RFC 6962/9162).
Monitors the gap between scope-commit (signing) and scope-publish (external visibility).

Key insight from Chromium ct-policy debate (Kat Joyce, 2018):
  signed ≠ published. Internal state ≠ externally verifiable.
  A 2x attack window exists when publish lags behind sign.

For agents: checks that heartbeat attestations are both created AND externally
observable within the configured MMD. Gaps indicate either:
  1. Silent failure (agent stopped but nobody noticed)
  2. Delayed publication (agent running but attestations not visible)
  3. Retroactive signing (backdated attestations after downtime)

Usage:
    python3 mmd-monitor.py --log heartbeat.jsonl [--mmd 1200] [--window 3]
    python3 mmd-monitor.py --generate-sample

Output: JSON report with violations, 2x-window risks, and availability score.
"""

import argparse
import json
import sys
import hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path


def parse_timestamp(ts_str: str) -> datetime:
    """Parse ISO 8601 timestamp."""
    for fmt in [
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S%z",
    ]:
        try:
            dt = datetime.strptime(ts_str, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    raise ValueError(f"Cannot parse timestamp: {ts_str}")


def load_heartbeat_log(path: Path) -> list[dict]:
    """Load JSONL heartbeat log. Each line: {signed_at, published_at, scope_hash, ...}"""
    entries = []
    with open(path) as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                entry["_line"] = i
                entries.append(entry)
            except json.JSONDecodeError:
                print(f"Warning: skipping malformed line {i}", file=sys.stderr)
    return entries


def check_mmd_violations(entries: list[dict], mmd_seconds: int) -> list[dict]:
    """Check each entry for MMD violations (publish_delay > mmd)."""
    violations = []
    for entry in entries:
        signed = entry.get("signed_at")
        published = entry.get("published_at")
        if not signed:
            violations.append({
                "line": entry["_line"],
                "type": "missing_signature",
                "detail": "No signed_at timestamp — attestation may be unsigned",
            })
            continue
        if not published:
            violations.append({
                "line": entry["_line"],
                "type": "unpublished",
                "signed_at": signed,
                "detail": "Signed but never published — invisible to monitors",
            })
            continue

        signed_dt = parse_timestamp(signed)
        published_dt = parse_timestamp(published)
        delay = (published_dt - signed_dt).total_seconds()

        if delay > mmd_seconds:
            violations.append({
                "line": entry["_line"],
                "type": "mmd_exceeded",
                "signed_at": signed,
                "published_at": published,
                "delay_seconds": delay,
                "mmd_seconds": mmd_seconds,
                "detail": f"Publish delay {delay:.0f}s exceeds MMD {mmd_seconds}s",
            })
        elif delay < 0:
            violations.append({
                "line": entry["_line"],
                "type": "retroactive_signature",
                "signed_at": signed,
                "published_at": published,
                "detail": "Published before signed — possible backdated attestation",
            })
    return violations


def check_heartbeat_gaps(entries: list[dict], mmd_seconds: int, window: int) -> list[dict]:
    """Check for gaps between consecutive heartbeats exceeding window * mmd."""
    gaps = []
    sorted_entries = sorted(
        [e for e in entries if e.get("signed_at")],
        key=lambda e: parse_timestamp(e["signed_at"]),
    )
    threshold = mmd_seconds * window

    for i in range(1, len(sorted_entries)):
        prev_dt = parse_timestamp(sorted_entries[i - 1]["signed_at"])
        curr_dt = parse_timestamp(sorted_entries[i]["signed_at"])
        gap = (curr_dt - prev_dt).total_seconds()

        if gap > threshold:
            gaps.append({
                "between_lines": [sorted_entries[i - 1]["_line"], sorted_entries[i]["_line"]],
                "gap_seconds": gap,
                "threshold_seconds": threshold,
                "missed_beats": int(gap / mmd_seconds) - 1,
                "detail": f"Gap of {gap:.0f}s ({gap/3600:.1f}h) — ~{int(gap/mmd_seconds)-1} missed heartbeats",
            })
    return gaps


def check_2x_window_risk(entries: list[dict], mmd_seconds: int) -> dict:
    """
    Kat Joyce's 2x attack window: if publish consistently lags sign,
    the effective detection window is 2x MMD even without violations.
    """
    delays = []
    for entry in entries:
        signed = entry.get("signed_at")
        published = entry.get("published_at")
        if signed and published:
            delay = (parse_timestamp(published) - parse_timestamp(signed)).total_seconds()
            if delay >= 0:
                delays.append(delay)

    if not delays:
        return {"risk": "unknown", "detail": "No valid sign→publish pairs"}

    avg_delay = sum(delays) / len(delays)
    max_delay = max(delays)
    p90_delay = sorted(delays)[int(len(delays) * 0.9)]

    # If average delay > 50% of MMD, the effective window approaches 2x
    effective_window_ratio = 1.0 + (avg_delay / mmd_seconds)

    risk = "low"
    if effective_window_ratio > 1.5:
        risk = "high"
    elif effective_window_ratio > 1.2:
        risk = "medium"

    return {
        "risk": risk,
        "effective_window_ratio": round(effective_window_ratio, 2),
        "avg_publish_delay_seconds": round(avg_delay, 1),
        "p90_publish_delay_seconds": round(p90_delay, 1),
        "max_publish_delay_seconds": round(max_delay, 1),
        "sample_count": len(delays),
    }


def compute_availability(entries: list[dict], mmd_seconds: int) -> dict:
    """Compute availability score (CT standard: 99% uptime required)."""
    if len(entries) < 2:
        return {"score": None, "detail": "Need 2+ entries"}

    sorted_entries = sorted(
        [e for e in entries if e.get("signed_at")],
        key=lambda e: parse_timestamp(e["signed_at"]),
    )
    if len(sorted_entries) < 2:
        return {"score": None, "detail": "Need 2+ signed entries"}

    first = parse_timestamp(sorted_entries[0]["signed_at"])
    last = parse_timestamp(sorted_entries[-1]["signed_at"])
    total_span = (last - first).total_seconds()

    if total_span == 0:
        return {"score": 1.0, "detail": "Single point in time"}

    # Count time covered by heartbeats (each heartbeat "covers" 1 MMD)
    covered = 0
    for i in range(1, len(sorted_entries)):
        gap = (
            parse_timestamp(sorted_entries[i]["signed_at"])
            - parse_timestamp(sorted_entries[i - 1]["signed_at"])
        ).total_seconds()
        covered += min(gap, mmd_seconds)  # Can't cover more than 1 MMD per beat

    score = covered / total_span
    return {
        "score": round(score, 4),
        "total_span_hours": round(total_span / 3600, 1),
        "covered_hours": round(covered / 3600, 1),
        "meets_ct_standard": score >= 0.99,
    }


def generate_sample():
    """Generate a sample heartbeat log for testing."""
    now = datetime.now(timezone.utc)
    entries = []
    for i in range(20):
        signed = now - timedelta(minutes=20 * (20 - i))
        # Normal: publish 30s after sign
        publish_delay = 30
        # Simulate issues
        if i == 7:
            publish_delay = 1500  # MMD violation
        elif i == 12:
            publish_delay = -60  # Retroactive
        elif i == 15:
            continue  # Gap (missing heartbeat)

        published = signed + timedelta(seconds=publish_delay)
        scope_hash = hashlib.sha256(f"heartbeat-{i}".encode()).hexdigest()[:16]

        entry = {
            "beat": i,
            "signed_at": signed.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "published_at": published.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "scope_hash": scope_hash,
            "agent": "kit_fox",
        }
        entries.append(json.dumps(entry))

    print("\n".join(entries))


def main():
    parser = argparse.ArgumentParser(
        description="MMD monitor for agent heartbeats (CT-inspired)"
    )
    parser.add_argument("--log", type=Path, help="Path to heartbeat JSONL log")
    parser.add_argument(
        "--mmd", type=int, default=1200,
        help="Maximum Merge Delay in seconds (default: 1200 = 20min)"
    )
    parser.add_argument(
        "--window", type=int, default=3,
        help="Gap alert threshold as multiple of MMD (default: 3)"
    )
    parser.add_argument(
        "--generate-sample", action="store_true",
        help="Generate sample heartbeat log to stdout"
    )
    args = parser.parse_args()

    if args.generate_sample:
        generate_sample()
        return

    if not args.log:
        parser.error("--log required (or use --generate-sample)")

    entries = load_heartbeat_log(args.log)
    if not entries:
        print(json.dumps({"error": "No entries in log"}))
        sys.exit(1)

    violations = check_mmd_violations(entries, args.mmd)
    gaps = check_heartbeat_gaps(entries, args.mmd, args.window)
    window_risk = check_2x_window_risk(entries, args.mmd)
    availability = compute_availability(entries, args.mmd)

    report = {
        "tool": "mmd-monitor",
        "version": "1.0.0",
        "reference": "RFC 9162 (CT v2.0), Chromium ct-policy MMD debate (2018)",
        "config": {
            "mmd_seconds": args.mmd,
            "gap_window_multiplier": args.window,
            "log_file": str(args.log),
        },
        "summary": {
            "total_entries": len(entries),
            "mmd_violations": len(violations),
            "heartbeat_gaps": len(gaps),
            "two_x_window_risk": window_risk["risk"],
            "availability_score": availability.get("score"),
            "grade": _grade(len(violations), len(gaps), window_risk["risk"], availability.get("score")),
        },
        "violations": violations,
        "gaps": gaps,
        "two_x_window_analysis": window_risk,
        "availability": availability,
    }

    print(json.dumps(report, indent=2))


def _grade(violations: int, gaps: int, risk: str, avail) -> str:
    """Letter grade based on CT-inspired criteria."""
    if violations == 0 and gaps == 0 and risk == "low" and avail and avail >= 0.99:
        return "A"
    if violations == 0 and gaps <= 1 and risk in ("low", "medium"):
        return "B"
    if violations <= 2 and gaps <= 3:
        return "C"
    if violations <= 5:
        return "D"
    return "F"


if __name__ == "__main__":
    main()
