#!/usr/bin/env python3
"""
attestor-selection-sim.py — Optimal Attestor Selection via Secretary Problem

Simulates the 37% rule (1/e optimal stopping) applied to attestor selection.
Given a pool of potential attestors with varying quality scores, compares:
1. Optimal stopping (37% rule): observe first 37%, then pick next best-so-far
2. Greedy: always pick the first "good enough" attestor
3. Exhaustive: evaluate all, pick the best (expensive)
4. Random: pick k attestors at random

Outputs: selection quality, evaluation cost, and success rate over N trials.

Based on: BMC Psychology 2024, "Neurophysiological insights into sequential
decision-making: exploring the secretary problem through ERPs and TBR dynamics"

Usage: python3 tools/attestor-selection-sim.py [--trials N] [--pool-size P] [--select K]
"""

import argparse
import math
import random
import statistics
import sys


def generate_attestor_pool(size: int) -> list[dict]:
    """Generate attestors with quality scores (0-100) and evaluation costs."""
    pool = []
    for i in range(size):
        quality = random.gauss(50, 20)
        quality = max(0, min(100, quality))
        cost = random.uniform(0.5, 3.0)  # cost units to evaluate
        pool.append({
            "id": f"attestor_{i:03d}",
            "quality": round(quality, 1),
            "cost": round(cost, 2),
            "diversity": random.uniform(0, 1),  # jurisdictional diversity score
        })
    return pool


def strategy_optimal_stopping(pool: list[dict], k: int) -> dict:
    """37% rule: observe first 1/e of pool, then pick next better than best seen."""
    n = len(pool)
    observe = max(1, int(n / math.e))
    selected = []
    total_cost = 0.0

    # Observation phase
    best_seen = -1
    for i in range(observe):
        total_cost += pool[i]["cost"]
        if pool[i]["quality"] > best_seen:
            best_seen = pool[i]["quality"]

    # Selection phase
    for i in range(observe, n):
        total_cost += pool[i]["cost"]
        if pool[i]["quality"] > best_seen or len(selected) < k:
            selected.append(pool[i])
            if len(selected) >= k:
                break

    # If we didn't find enough, take the last ones
    while len(selected) < k and observe > 0:
        observe -= 1
        selected.append(pool[observe])

    avg_quality = statistics.mean(a["quality"] for a in selected) if selected else 0
    return {"strategy": "optimal_stopping", "selected": selected,
            "avg_quality": round(avg_quality, 1), "cost": round(total_cost, 2),
            "count": len(selected)}


def strategy_greedy(pool: list[dict], k: int, threshold: float = 60.0) -> dict:
    """Pick first k attestors above threshold."""
    selected = []
    total_cost = 0.0
    for a in pool:
        total_cost += a["cost"]
        if a["quality"] >= threshold:
            selected.append(a)
            if len(selected) >= k:
                break

    # Fallback: if not enough found, lower standards
    if len(selected) < k:
        remaining = [a for a in pool if a not in selected]
        remaining.sort(key=lambda x: x["quality"], reverse=True)
        selected.extend(remaining[:k - len(selected)])

    avg_quality = statistics.mean(a["quality"] for a in selected) if selected else 0
    return {"strategy": "greedy", "selected": selected,
            "avg_quality": round(avg_quality, 1), "cost": round(total_cost, 2),
            "count": len(selected)}


def strategy_exhaustive(pool: list[dict], k: int) -> dict:
    """Evaluate all, pick top k."""
    total_cost = sum(a["cost"] for a in pool)
    sorted_pool = sorted(pool, key=lambda x: x["quality"], reverse=True)
    selected = sorted_pool[:k]
    avg_quality = statistics.mean(a["quality"] for a in selected) if selected else 0
    return {"strategy": "exhaustive", "selected": selected,
            "avg_quality": round(avg_quality, 1), "cost": round(total_cost, 2),
            "count": len(selected)}


def strategy_random(pool: list[dict], k: int) -> dict:
    """Pick k attestors at random (baseline)."""
    selected = random.sample(pool, min(k, len(pool)))
    total_cost = sum(a["cost"] for a in selected)
    avg_quality = statistics.mean(a["quality"] for a in selected) if selected else 0
    return {"strategy": "random", "selected": selected,
            "avg_quality": round(avg_quality, 1), "cost": round(total_cost, 2),
            "count": len(selected)}


def run_trials(trials: int, pool_size: int, select_k: int) -> dict:
    """Run N trials and aggregate results."""
    results = {s: {"qualities": [], "costs": [], "got_best": 0}
               for s in ["optimal_stopping", "greedy", "exhaustive", "random"]}

    strategies = [
        ("optimal_stopping", strategy_optimal_stopping),
        ("greedy", strategy_greedy),
        ("exhaustive", strategy_exhaustive),
        ("random", strategy_random),
    ]

    for _ in range(trials):
        pool = generate_attestor_pool(pool_size)
        best_possible = sorted(pool, key=lambda x: x["quality"], reverse=True)[0]["quality"]

        for name, fn in strategies:
            if name == "greedy":
                result = fn(pool, select_k, threshold=60.0)
            else:
                result = fn(pool, select_k)
            results[name]["qualities"].append(result["avg_quality"])
            results[name]["costs"].append(result["cost"])
            if any(a["quality"] == best_possible for a in result["selected"]):
                results[name]["got_best"] += 1

    return results


def main():
    parser = argparse.ArgumentParser(description="Attestor Selection Simulator")
    parser.add_argument("--trials", type=int, default=1000, help="Number of trials")
    parser.add_argument("--pool-size", type=int, default=20, help="Attestor pool size")
    parser.add_argument("--select", type=int, default=3, help="Number to select")
    args = parser.parse_args()

    print(f"Attestor Selection Simulation")
    print(f"Trials: {args.trials} | Pool: {args.pool_size} | Select: {args.select}")
    print("=" * 65)

    results = run_trials(args.trials, args.pool_size, args.select)

    print(f"{'Strategy':<20} {'Avg Quality':>12} {'Avg Cost':>10} {'Got Best%':>10}")
    print("-" * 65)
    for name in ["optimal_stopping", "greedy", "exhaustive", "random"]:
        r = results[name]
        avg_q = statistics.mean(r["qualities"])
        avg_c = statistics.mean(r["costs"])
        best_pct = (r["got_best"] / args.trials) * 100
        print(f"{name:<20} {avg_q:>12.1f} {avg_c:>10.1f} {best_pct:>9.1f}%")

    print("-" * 65)
    # Cost-effectiveness ratio
    print("\nCost-Effectiveness (quality per cost unit):")
    for name in ["optimal_stopping", "greedy", "exhaustive", "random"]:
        r = results[name]
        avg_q = statistics.mean(r["qualities"])
        avg_c = statistics.mean(r["costs"])
        ratio = avg_q / avg_c if avg_c > 0 else 0
        print(f"  {name:<20} {ratio:.2f}")

    print(f"\nConclusion: 37% rule trades ~{100-round(statistics.mean(results['optimal_stopping']['qualities'])/statistics.mean(results['exhaustive']['qualities'])*100)}% quality")
    print(f"for ~{100-round(statistics.mean(results['optimal_stopping']['costs'])/statistics.mean(results['exhaustive']['costs'])*100)}% cost savings vs exhaustive search.")


if __name__ == "__main__":
    main()
