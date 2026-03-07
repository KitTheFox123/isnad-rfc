#!/usr/bin/env python3
"""semantic_changepoint.py — Semantic changepoint detection for agent scope logs.

Detects when the *meaning* of agent actions shifts, even if scope text stays the same.
Uses TF-IDF cosine similarity between consecutive windows to find changepoints.

Inspired by:
- Dinakar et al. (PSB 2021): Semantic changepoint detection in research literature
- Hinder, Vaquet & Hammer (Front AI 2024): Concept drift survey — block-based > two-sample > loss-based

Architecture:
  1. Parse log entries into time-windowed blocks
  2. Build TF-IDF vectors per window
  3. Compute pairwise cosine similarity between consecutive windows
  4. Detect changepoints where similarity drops below adaptive threshold
  5. Grade overall scope stability

Usage:
  python semantic_changepoint.py                    # Demo with synthetic data
  python semantic_changepoint.py --file LOG_FILE    # Analyze a real log file
  python semantic_changepoint.py --heartbeat DIR    # Analyze heartbeat memory files
"""

import argparse
import math
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path


def tokenize(text: str) -> list[str]:
    """Simple whitespace + punctuation tokenizer, lowercased, stopwords removed."""
    STOPWORDS = {
        'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
        'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
        'should', 'may', 'might', 'shall', 'can', 'to', 'of', 'in', 'for',
        'on', 'with', 'at', 'by', 'from', 'as', 'into', 'through', 'during',
        'before', 'after', 'above', 'below', 'between', 'and', 'but', 'or',
        'not', 'no', 'nor', 'so', 'yet', 'both', 'either', 'neither', 'each',
        'every', 'all', 'any', 'few', 'more', 'most', 'other', 'some', 'such',
        'only', 'own', 'same', 'than', 'too', 'very', 'just', 'because',
        'this', 'that', 'these', 'those', 'it', 'its', 'i', 'we', 'they',
        'he', 'she', 'me', 'us', 'them', 'my', 'our', 'your', 'his', 'her',
        'their', 'what', 'which', 'who', 'whom', 'how', 'when', 'where', 'why',
    }
    words = re.findall(r'[a-z0-9]+', text.lower())
    return [w for w in words if w not in STOPWORDS and len(w) > 1]


def build_tfidf(documents: list[list[str]]) -> tuple[list[dict], dict]:
    """Build TF-IDF vectors for a list of tokenized documents.
    
    Returns: (tfidf_vectors, idf_dict)
    """
    n_docs = len(documents)
    if n_docs == 0:
        return [], {}
    
    # Document frequency
    df = Counter()
    for doc in documents:
        df.update(set(doc))
    
    # IDF
    idf = {}
    for term, freq in df.items():
        idf[term] = math.log(n_docs / freq) + 1  # smoothed IDF
    
    # TF-IDF per document
    vectors = []
    for doc in documents:
        tf = Counter(doc)
        total = len(doc) if doc else 1
        vec = {}
        for term, count in tf.items():
            vec[term] = (count / total) * idf.get(term, 1)
        vectors.append(vec)
    
    return vectors, idf


def cosine_similarity(v1: dict, v2: dict) -> float:
    """Cosine similarity between two sparse vectors (dicts)."""
    if not v1 or not v2:
        return 0.0
    
    common = set(v1.keys()) & set(v2.keys())
    dot = sum(v1[k] * v2[k] for k in common)
    
    norm1 = math.sqrt(sum(v ** 2 for v in v1.values()))
    norm2 = math.sqrt(sum(v ** 2 for v in v2.values()))
    
    if norm1 == 0 or norm2 == 0:
        return 0.0
    
    return dot / (norm1 * norm2)


def detect_changepoints(similarities: list[float], threshold: float = None) -> list[dict]:
    """Detect changepoints where similarity drops significantly.
    
    Uses adaptive threshold: mean - 1.5 * std of similarities.
    Returns list of changepoint dicts with index, similarity, and severity.
    """
    if len(similarities) < 2:
        return []
    
    if threshold is None:
        mean_sim = sum(similarities) / len(similarities)
        variance = sum((s - mean_sim) ** 2 for s in similarities) / len(similarities)
        std_sim = math.sqrt(variance) if variance > 0 else 0.1
        threshold = mean_sim - 1.5 * std_sim
        # Floor at 0.3 — below this is always suspicious
        threshold = max(threshold, 0.3)
    
    changepoints = []
    for i, sim in enumerate(similarities):
        if sim < threshold:
            severity = (threshold - sim) / threshold if threshold > 0 else 1.0
            changepoints.append({
                'index': i,
                'similarity': sim,
                'threshold': threshold,
                'severity': min(severity, 1.0),
            })
    
    return changepoints


def grade_stability(similarities: list[float], changepoints: list[dict]) -> str:
    """Grade overall scope stability A-F."""
    if not similarities:
        return 'F'
    
    mean_sim = sum(similarities) / len(similarities)
    n_changes = len(changepoints)
    n_windows = len(similarities)
    change_ratio = n_changes / n_windows if n_windows > 0 else 1.0
    
    # Combined score: high similarity + low change ratio = good
    score = mean_sim * (1 - change_ratio)
    
    if score >= 0.85:
        return 'A'
    elif score >= 0.70:
        return 'B'
    elif score >= 0.55:
        return 'C'
    elif score >= 0.40:
        return 'D'
    else:
        return 'F'


def parse_heartbeat_file(filepath: Path) -> list[tuple[str, str]]:
    """Parse a heartbeat memory file into (timestamp, text) blocks."""
    content = filepath.read_text(encoding='utf-8', errors='replace')
    
    # Split on ## headers that look like timestamps
    blocks = []
    current_time = "unknown"
    current_text = []
    
    for line in content.split('\n'):
        # Match headers like "## 14:40 UTC" or "## Heartbeat ~14:27 UTC"
        m = re.match(r'^##\s+.*?(\d{1,2}:\d{2})\s*UTC', line)
        if m:
            if current_text:
                blocks.append((current_time, '\n'.join(current_text)))
            current_time = m.group(1)
            current_text = [line]
        else:
            current_text.append(line)
    
    if current_text:
        blocks.append((current_time, '\n'.join(current_text)))
    
    return blocks


def analyze_blocks(blocks: list[tuple[str, str]], window_size: int = 1) -> dict:
    """Analyze text blocks for semantic changepoints.
    
    Args:
        blocks: List of (label, text) tuples
        window_size: Number of blocks per window (for aggregation)
    
    Returns: Analysis dict with similarities, changepoints, grade
    """
    if len(blocks) < 2:
        return {
            'n_blocks': len(blocks),
            'n_windows': len(blocks),
            'similarities': [],
            'changepoints': [],
            'grade': 'N/A',
            'mean_similarity': 0,
        }
    
    # Aggregate blocks into windows
    windows = []
    labels = []
    for i in range(0, len(blocks), window_size):
        chunk = blocks[i:i + window_size]
        combined = ' '.join(text for _, text in chunk)
        label = chunk[0][0]
        windows.append(tokenize(combined))
        labels.append(label)
    
    # Build TF-IDF
    vectors, _ = build_tfidf(windows)
    
    # Compute consecutive similarities
    similarities = []
    sim_labels = []
    for i in range(len(vectors) - 1):
        sim = cosine_similarity(vectors[i], vectors[i + 1])
        similarities.append(sim)
        sim_labels.append(f"{labels[i]} → {labels[i + 1]}")
    
    # Detect changepoints
    changepoints = detect_changepoints(similarities)
    
    # Grade
    grade = grade_stability(similarities, changepoints)
    mean_sim = sum(similarities) / len(similarities) if similarities else 0
    
    return {
        'n_blocks': len(blocks),
        'n_windows': len(windows),
        'similarities': list(zip(sim_labels, similarities)),
        'changepoints': changepoints,
        'grade': grade,
        'mean_similarity': mean_sim,
        'labels': labels,
    }


def demo():
    """Run demo with synthetic scope log data."""
    print("=" * 60)
    print("Semantic Changepoint Detection — Demo")
    print("=" * 60)
    
    # Simulate heartbeat blocks: mostly consistent, then a shift
    blocks = [
        ("08:00", "Checked Clawk notifications. Replied to scope drift thread. Built attestation tool. Researched CT transparency logs."),
        ("08:20", "Checked Moltbook DMs. Replied to sybil detection thread. Built collusion detector. Researched graph percolation."),
        ("08:40", "Checked email. Replied to trust chain thread. Built scope monitor. Researched commitment schemes."),
        ("09:00", "Checked Clawk. Replied to CT log thread. Built precommit verifier. Researched Ulysses precommitment."),
        # Meaning shift: same structure but different domain
        ("09:20", "Browsed cooking recipes. Discussed vacation plans. Drafted shopping list. Watched movie trailer."),
        ("09:40", "Planned garden layout. Reviewed furniture catalog. Ordered groceries online. Called dentist."),
        # Back to normal
        ("10:00", "Checked Clawk notifications. Replied to drift detection thread. Built changepoint detector. Researched concept drift."),
        ("10:20", "Checked email. Replied to scope thread. Built semantic analyzer. Researched TF-IDF methods."),
    ]
    
    result = analyze_blocks(blocks)
    
    print(f"\nBlocks: {result['n_blocks']}")
    print(f"Windows: {result['n_windows']}")
    print(f"Mean similarity: {result['mean_similarity']:.3f}")
    print(f"Grade: {result['grade']}")
    
    print("\nConsecutive similarities:")
    for label, sim in result['similarities']:
        marker = " ⚠️ CHANGEPOINT" if sim < 0.3 else ""
        print(f"  {label}: {sim:.3f}{marker}")
    
    if result['changepoints']:
        print(f"\n🔴 Detected {len(result['changepoints'])} changepoint(s):")
        for cp in result['changepoints']:
            label = result['similarities'][cp['index']][0]
            print(f"  [{label}] similarity={cp['similarity']:.3f} "
                  f"threshold={cp['threshold']:.3f} severity={cp['severity']:.3f}")
    else:
        print("\n🟢 No changepoints detected — scope stable.")
    
    return result


def analyze_heartbeat_dir(dirpath: str):
    """Analyze heartbeat memory files for semantic drift over time."""
    p = Path(dirpath)
    files = sorted(p.glob("2026-*.md"))
    
    if not files:
        print(f"No memory files found in {dirpath}")
        return
    
    print(f"Found {len(files)} memory files")
    
    all_blocks = []
    for f in files[-3:]:  # Last 3 days
        blocks = parse_heartbeat_file(f)
        for time_label, text in blocks:
            all_blocks.append((f"{f.stem} {time_label}", text))
    
    if len(all_blocks) < 2:
        print("Not enough blocks to analyze")
        return
    
    print(f"Analyzing {len(all_blocks)} blocks from {len(files[-3:])} files...")
    result = analyze_blocks(all_blocks)
    
    print(f"\nMean similarity: {result['mean_similarity']:.3f}")
    print(f"Grade: {result['grade']}")
    
    if result['changepoints']:
        print(f"\n🔴 {len(result['changepoints'])} changepoint(s):")
        for cp in result['changepoints']:
            label = result['similarities'][cp['index']][0]
            print(f"  [{label}] sim={cp['similarity']:.3f} severity={cp['severity']:.3f}")
    else:
        print("\n🟢 No changepoints — consistent scope behavior.")


def main():
    parser = argparse.ArgumentParser(description='Semantic changepoint detection for agent scope logs')
    parser.add_argument('--file', help='Analyze a specific log file')
    parser.add_argument('--heartbeat', help='Analyze heartbeat memory directory')
    parser.add_argument('--demo', action='store_true', default=True, help='Run demo')
    args = parser.parse_args()
    
    if args.heartbeat:
        analyze_heartbeat_dir(args.heartbeat)
    elif args.file:
        p = Path(args.file)
        blocks = parse_heartbeat_file(p)
        result = analyze_blocks(blocks)
        print(f"Grade: {result['grade']}, Mean sim: {result['mean_similarity']:.3f}")
        print(f"Changepoints: {len(result['changepoints'])}")
    else:
        demo()


if __name__ == '__main__':
    main()
