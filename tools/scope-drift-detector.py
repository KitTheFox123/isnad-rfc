#!/usr/bin/env python3
"""scope-drift-detector.py — Detect when scope context drifts from original intent.

Compares the semantic environment at scope-issuance time vs current environment.
Uses TF-IDF cosine similarity as a lightweight proxy for contextual semantic shift
(inspired by Montanelli & Periti 2024, arXiv:2304.01666).

The insight: an agent can stay perfectly in-scope (binary check passes) while the
MEANING of that scope has drifted because the environment changed. "Monitor the
network" means something different before and after a breach.

Usage:
    python scope-drift-detector.py --baseline HEARTBEAT_v1.md --current HEARTBEAT_v2.md
    python scope-drift-detector.py --baseline-text "monitor network health" --context-log actions.jsonl

Outputs drift score (0.0 = identical context, 1.0 = completely different) and
recommends scope renewal when drift exceeds threshold.
"""

import argparse
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path


def tokenize(text: str) -> list[str]:
    """Simple whitespace + punctuation tokenizer."""
    return re.findall(r'\b[a-z][a-z0-9]+\b', text.lower())


def tf_idf_vector(tokens: list[str], idf: dict[str, float]) -> dict[str, float]:
    """Compute TF-IDF vector for a token list."""
    tf = Counter(tokens)
    total = len(tokens) if tokens else 1
    return {t: (count / total) * idf.get(t, 1.0) for t, count in tf.items()}


def cosine_similarity(v1: dict[str, float], v2: dict[str, float]) -> float:
    """Cosine similarity between two sparse vectors."""
    keys = set(v1) | set(v2)
    dot = sum(v1.get(k, 0) * v2.get(k, 0) for k in keys)
    mag1 = math.sqrt(sum(v ** 2 for v in v1.values())) or 1e-10
    mag2 = math.sqrt(sum(v ** 2 for v in v2.values())) or 1e-10
    return dot / (mag1 * mag2)


def compute_idf(docs: list[list[str]]) -> dict[str, float]:
    """Compute IDF across document collection."""
    n = len(docs) if docs else 1
    df = Counter()
    for doc in docs:
        df.update(set(doc))
    return {t: math.log(n / (count + 1)) + 1 for t, count in df.items()}


def load_text(path: str) -> str:
    """Load text from file."""
    return Path(path).read_text(encoding='utf-8')


def load_jsonl_contexts(path: str) -> list[str]:
    """Load context strings from JSONL action log."""
    contexts = []
    with open(path, encoding='utf-8') as f:
        for line in f:
            try:
                entry = json.loads(line.strip())
                # Extract any text-like fields
                for key in ('action', 'description', 'context', 'scope', 'content'):
                    if key in entry and isinstance(entry[key], str):
                        contexts.append(entry[key])
            except (json.JSONDecodeError, KeyError):
                continue
    return contexts


def analyze_drift(baseline_text: str, current_text: str, 
                  threshold: float = 0.3) -> dict:
    """Analyze semantic drift between baseline scope and current context.
    
    Returns:
        dict with drift_score, similarity, renewal_recommended, details
    """
    baseline_tokens = tokenize(baseline_text)
    current_tokens = tokenize(current_text)
    
    if not baseline_tokens or not current_tokens:
        return {
            'drift_score': 1.0,
            'similarity': 0.0,
            'renewal_recommended': True,
            'reason': 'Empty baseline or current text',
            'baseline_terms': 0,
            'current_terms': 0,
        }
    
    # Compute IDF across both documents
    idf = compute_idf([baseline_tokens, current_tokens])
    
    # TF-IDF vectors
    v_baseline = tf_idf_vector(baseline_tokens, idf)
    v_current = tf_idf_vector(current_tokens, idf)
    
    similarity = cosine_similarity(v_baseline, v_current)
    drift_score = 1.0 - similarity
    
    # Find terms that appeared/disappeared
    baseline_set = set(baseline_tokens)
    current_set = set(current_tokens)
    new_terms = current_set - baseline_set
    lost_terms = baseline_set - current_set
    
    # Top novel terms by frequency
    current_tf = Counter(current_tokens)
    top_new = sorted(new_terms, key=lambda t: current_tf[t], reverse=True)[:10]
    
    baseline_tf = Counter(baseline_tokens)
    top_lost = sorted(lost_terms, key=lambda t: baseline_tf[t], reverse=True)[:10]
    
    result = {
        'drift_score': round(drift_score, 4),
        'similarity': round(similarity, 4),
        'renewal_recommended': drift_score > threshold,
        'threshold': threshold,
        'baseline_unique_terms': len(baseline_set),
        'current_unique_terms': len(current_set),
        'new_terms_count': len(new_terms),
        'lost_terms_count': len(lost_terms),
        'top_new_terms': top_new,
        'top_lost_terms': top_lost,
    }
    
    if drift_score > threshold:
        result['reason'] = (
            f'Drift {drift_score:.2%} exceeds threshold {threshold:.2%}. '
            f'Scope context has shifted significantly. '
            f'Top new concepts: {", ".join(top_new[:5]) if top_new else "none"}. '
            f'Recommend operator re-sign scope with updated context.'
        )
    else:
        result['reason'] = (
            f'Drift {drift_score:.2%} within threshold {threshold:.2%}. '
            f'Scope context remains stable.'
        )
    
    return result


def main():
    parser = argparse.ArgumentParser(
        description='Detect semantic drift between scope issuance and current context'
    )
    parser.add_argument('--baseline', help='Baseline scope file (e.g., original HEARTBEAT.md)')
    parser.add_argument('--current', help='Current context file (e.g., current HEARTBEAT.md)')
    parser.add_argument('--baseline-text', help='Baseline scope as inline text')
    parser.add_argument('--current-text', help='Current context as inline text')
    parser.add_argument('--context-log', help='JSONL action log for current context')
    parser.add_argument('--threshold', type=float, default=0.3,
                        help='Drift threshold for renewal recommendation (default: 0.3)')
    parser.add_argument('--json', action='store_true', help='Output as JSON')
    
    args = parser.parse_args()
    
    # Load baseline
    if args.baseline:
        baseline = load_text(args.baseline)
    elif args.baseline_text:
        baseline = args.baseline_text
    else:
        print("Error: provide --baseline or --baseline-text", file=sys.stderr)
        sys.exit(1)
    
    # Load current
    if args.current:
        current = load_text(args.current)
    elif args.current_text:
        current = args.current_text
    elif args.context_log:
        contexts = load_jsonl_contexts(args.context_log)
        current = ' '.join(contexts)
    else:
        print("Error: provide --current, --current-text, or --context-log", file=sys.stderr)
        sys.exit(1)
    
    result = analyze_drift(baseline, current, threshold=args.threshold)
    
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        icon = '🔴' if result['renewal_recommended'] else '🟢'
        print(f"{icon} Scope Drift Analysis")
        print(f"   Drift score: {result['drift_score']:.2%}")
        print(f"   Similarity:  {result['similarity']:.2%}")
        print(f"   Threshold:   {result['threshold']:.2%}")
        print(f"   Renewal:     {'RECOMMENDED' if result['renewal_recommended'] else 'not needed'}")
        print(f"   New terms:   {result['new_terms_count']}")
        print(f"   Lost terms:  {result['lost_terms_count']}")
        if result.get('top_new_terms'):
            print(f"   Top new:     {', '.join(result['top_new_terms'][:5])}")
        if result.get('top_lost_terms'):
            print(f"   Top lost:    {', '.join(result['top_lost_terms'][:5])}")
        print(f"\n   {result['reason']}")


if __name__ == '__main__':
    main()
