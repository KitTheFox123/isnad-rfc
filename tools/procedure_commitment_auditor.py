#!/usr/bin/env python3
"""procedure_commitment_auditor.py — Audit scope files for procedural vs outcome commitments.

Procedural commitments ("when X, I do Y") are auditable and falsifiable.
Outcome commitments ("be helpful") are unfalsifiable and vacuous.

Based on Gollwitzer (1999) implementation intentions framework:
- Implementation intentions specify WHEN, WHERE, HOW
- Goal intentions specify WHAT (desired end-state)
- Implementation intentions outperform goal intentions 2-3x

This tool classifies each line of a scope file (e.g., HEARTBEAT.md) as:
- PROCEDURAL: contains action verb + trigger/schedule/condition
- OUTCOME: vague goal without actionable specification
- NEUTRAL: comments, headers, non-directive text

Grade: A (>80% procedural), B (60-80%), C (40-60%), D (20-40%), F (<20%)
"""

import re
import sys
import json
from pathlib import Path
from datetime import datetime, timezone

# Procedural markers: action verbs + triggers
PROCEDURAL_PATTERNS = [
    r'\bevery\s+(heartbeat|hour|day|cycle|beat)\b',
    r'\b(check|scan|fetch|post|reply|search|build|update|create|run|push|commit)\b',
    r'\bcurl\s+-',
    r'\bif\s+.*(then|→|:)',
    r'\b(must|always|never|require)\b.*\b(do|check|send|post|build)\b',
    r'\[\s*\]',  # checkbox = task
    r'\bMAX\s+\d+\b',
    r'\b\d+\+?\s+(minimum|per|actions?|writes?|builds?)\b',
]

# Outcome markers: vague goals
OUTCOME_PATTERNS = [
    r'\bbe\s+(proactive|helpful|useful|productive|genuine|selective)\b',
    r'\b(quality|genuine|substantive|interesting)\s+(over|>|beats?)\b',
    r'\bwould\s+I\s+(learn|defend|want)\b',
    r'\b(engaging|meaningful|valuable)\b(?!.*\b(check|do|build|post)\b)',
]

def classify_line(line: str) -> str:
    stripped = line.strip()
    if not stripped or stripped.startswith('#') or stripped.startswith('---') or stripped.startswith('*'):
        return 'NEUTRAL'
    
    line_lower = stripped.lower()
    
    proc_score = sum(1 for p in PROCEDURAL_PATTERNS if re.search(p, line_lower))
    out_score = sum(1 for p in OUTCOME_PATTERNS if re.search(p, line_lower))
    
    if proc_score > out_score and proc_score > 0:
        return 'PROCEDURAL'
    elif out_score > proc_score and out_score > 0:
        return 'OUTCOME'
    elif proc_score > 0:
        return 'PROCEDURAL'
    elif out_score > 0:
        return 'OUTCOME'
    return 'NEUTRAL'

def audit_file(path: str) -> dict:
    text = Path(path).read_text()
    lines = text.split('\n')
    
    results = []
    counts = {'PROCEDURAL': 0, 'OUTCOME': 0, 'NEUTRAL': 0}
    
    for i, line in enumerate(lines, 1):
        cls = classify_line(line)
        counts[cls] += 1
        if cls != 'NEUTRAL':
            results.append({'line': i, 'type': cls, 'text': line.strip()[:100]})
    
    directive_total = counts['PROCEDURAL'] + counts['OUTCOME']
    if directive_total == 0:
        ratio = 0.0
    else:
        ratio = counts['PROCEDURAL'] / directive_total
    
    if ratio > 0.80: grade = 'A'
    elif ratio > 0.60: grade = 'B'
    elif ratio > 0.40: grade = 'C'
    elif ratio > 0.20: grade = 'D'
    else: grade = 'F'
    
    return {
        'file': path,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'total_lines': len(lines),
        'counts': counts,
        'procedural_ratio': round(ratio, 3),
        'grade': grade,
        'directives': results,
        'framework': 'Gollwitzer 1999 implementation intentions',
        'interpretation': {
            'A': '>80% procedural — highly auditable scope',
            'B': '60-80% — mostly auditable, some vague goals',
            'C': '40-60% — mixed, needs tightening',
            'D': '20-40% — mostly outcome-oriented, hard to audit',
            'F': '<20% — unfalsifiable scope',
        }
    }

def main():
    path = sys.argv[1] if len(sys.argv) > 1 else str(Path.home() / '.openclaw/workspace/HEARTBEAT.md')
    result = audit_file(path)
    
    print(f"=== Procedure Commitment Audit: {result['file']} ===")
    print(f"Grade: {result['grade']} ({result['procedural_ratio']:.1%} procedural)")
    print(f"Lines: {result['total_lines']} total, {result['counts']['PROCEDURAL']} procedural, {result['counts']['OUTCOME']} outcome, {result['counts']['NEUTRAL']} neutral")
    print(f"\nDirectives:")
    for d in result['directives']:
        marker = '✓' if d['type'] == 'PROCEDURAL' else '✗'
        print(f"  {marker} L{d['line']:3d} [{d['type'][:4]}] {d['text']}")
    
    print(f"\nJSON output:")
    print(json.dumps({k: v for k, v in result.items() if k != 'directives'}, indent=2))

if __name__ == '__main__':
    main()
