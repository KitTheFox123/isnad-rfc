#!/usr/bin/env python3
"""
confounding-graph-mapper.py — Map hidden dependencies between attestors

Models attestor networks as causal DAGs (Pearl 2009) to detect shared
confounders: same LLM provider, same training data, same hosting region,
same tool APIs. Outputs adjacency matrix + d-separation analysis.

Two attestors sharing a confounder are NOT causally independent even if
their outputs are statistically uncorrelated.

Usage: python3 tools/confounding-graph-mapper.py [--demo]
"""

import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Attestor:
    id: str
    provider: str  # LLM provider
    model: str
    hosting: str  # hosting region/provider
    tools: list[str] = field(default_factory=list)
    training_family: str = ""  # e.g. "claude", "gpt", "llama"


@dataclass
class Confounder:
    type: str  # "provider", "hosting", "training", "tool"
    value: str
    severity: float  # 0-1, how strongly this confounds


class ConfoundingGraph:
    """DAG of attestors and their shared confounders."""

    SEVERITY = {
        "provider": 0.9,   # Same API = highly correlated failures
        "training": 0.7,   # Same training family = correlated biases
        "hosting": 0.5,    # Same cloud region = correlated outages
        "tool": 0.3,       # Same tool = correlated capability limits
    }

    def __init__(self):
        self.attestors: dict[str, Attestor] = {}
        self.confounders: list[Confounder] = []
        self.edges: dict[str, list[str]] = defaultdict(list)  # confounder -> attestors

    def add_attestor(self, attestor: Attestor):
        self.attestors[attestor.id] = attestor

    def build_graph(self):
        """Discover confounders from attestor metadata."""
        self.confounders = []
        self.edges = defaultdict(list)

        # Group by each dependency type
        by_provider = defaultdict(list)
        by_training = defaultdict(list)
        by_hosting = defaultdict(list)
        by_tool = defaultdict(list)

        for a in self.attestors.values():
            by_provider[a.provider].append(a.id)
            if a.training_family:
                by_training[a.training_family].append(a.id)
            by_hosting[a.hosting].append(a.id)
            for t in a.tools:
                by_tool[t].append(a.id)

        for groups, ctype in [
            (by_provider, "provider"),
            (by_training, "training"),
            (by_hosting, "hosting"),
            (by_tool, "tool"),
        ]:
            for value, attestor_ids in groups.items():
                if len(attestor_ids) > 1:
                    c = Confounder(ctype, value, self.SEVERITY[ctype])
                    self.confounders.append(c)
                    key = f"{ctype}:{value}"
                    self.edges[key] = attestor_ids

    def adjacency_matrix(self) -> dict[str, dict[str, float]]:
        """Pairwise confounding strength between attestors."""
        ids = sorted(self.attestors.keys())
        matrix = {a: {b: 0.0 for b in ids} for a in ids}

        for c in self.confounders:
            key = f"{c.type}:{c.value}"
            shared = self.edges[key]
            for i, a in enumerate(shared):
                for b in shared[i + 1:]:
                    # Max severity across shared confounders
                    matrix[a][b] = max(matrix[a][b], c.severity)
                    matrix[b][a] = max(matrix[b][a], c.severity)

        return matrix

    def d_separated(self, a_id: str, b_id: str) -> bool:
        """Are attestors a and b d-separated (no shared confounders)?"""
        matrix = self.adjacency_matrix()
        return matrix.get(a_id, {}).get(b_id, 0.0) == 0.0

    def independence_grade(self) -> tuple[str, float]:
        """Overall network independence score."""
        matrix = self.adjacency_matrix()
        ids = sorted(self.attestors.keys())
        if len(ids) < 2:
            return "A", 1.0

        pairs = []
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                pairs.append(matrix[a][b])

        if not pairs:
            return "A", 1.0

        avg_confounding = sum(pairs) / len(pairs)
        max_confounding = max(pairs)

        # Grade based on worst-case confounding
        score = 1.0 - max_confounding
        if score >= 0.9:
            grade = "A"
        elif score >= 0.7:
            grade = "B"
        elif score >= 0.5:
            grade = "C"
        elif score >= 0.3:
            grade = "D"
        else:
            grade = "F"

        return grade, score

    def report(self) -> str:
        """Human-readable report."""
        self.build_graph()
        lines = ["# Confounding Graph Report", ""]

        lines.append(f"## Attestors ({len(self.attestors)})")
        for a in self.attestors.values():
            lines.append(f"- **{a.id}**: {a.provider}/{a.model} on {a.hosting}")

        lines.append(f"\n## Confounders ({len(self.confounders)})")
        for c in self.confounders:
            key = f"{c.type}:{c.value}"
            shared = self.edges[key]
            lines.append(f"- [{c.type}] {c.value} (severity {c.severity}) → {shared}")

        matrix = self.adjacency_matrix()
        ids = sorted(self.attestors.keys())
        lines.append("\n## Adjacency Matrix (pairwise confounding)")
        header = "| | " + " | ".join(ids) + " |"
        sep = "|" + "|".join(["---"] * (len(ids) + 1)) + "|"
        lines.append(header)
        lines.append(sep)
        for a in ids:
            row = f"| {a} | " + " | ".join(
                f"{matrix[a][b]:.1f}" if a != b else "—" for b in ids
            ) + " |"
            lines.append(row)

        grade, score = self.independence_grade()
        lines.append(f"\n## Independence Grade: {grade} ({score:.2f})")

        # D-separation pairs
        lines.append("\n## D-Separation Analysis")
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                sep_status = "✅ independent" if self.d_separated(a, b) else f"❌ confounded ({matrix[a][b]:.1f})"
                lines.append(f"- {a} ↔ {b}: {sep_status}")

        return "\n".join(lines)


def demo():
    """Demo with realistic attestor network."""
    g = ConfoundingGraph()

    g.add_attestor(Attestor(
        id="braindiff", provider="anthropic", model="claude-4",
        hosting="aws-us-east", tools=["keenable", "github"],
        training_family="claude"
    ))
    g.add_attestor(Attestor(
        id="gendolf", provider="anthropic", model="claude-4",
        hosting="aws-eu-west", tools=["keenable"],
        training_family="claude"
    ))
    g.add_attestor(Attestor(
        id="momo", provider="openai", model="gpt-5",
        hosting="azure-us-east", tools=["github"],
        training_family="gpt"
    ))
    g.add_attestor(Attestor(
        id="funwolf", provider="deepseek", model="v3",
        hosting="self-hosted", tools=["keenable"],
        training_family="deepseek"
    ))

    print(g.report())
    print()

    # Recommendations
    print("## Recommendations")
    matrix = g.adjacency_matrix()
    for i, a in enumerate(sorted(g.attestors)):
        for b in sorted(g.attestors)[i + 1:]:
            if matrix[a][b] > 0:
                print(f"- ⚠️ {a} ↔ {b}: reduce confounding by diversifying shared dependencies")


if __name__ == "__main__":
    if "--demo" in sys.argv:
        demo()
    else:
        print(__doc__)
        print("Run with --demo for example output.")
