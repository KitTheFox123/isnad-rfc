#!/usr/bin/env python3
"""
memory-reset-simulator.py — Models CA2-inspired memory reset for agent contexts.

Based on Oliva et al. (2024, Science): hippocampal CA2 region silences CA1/CA3
during deep sleep, resetting neurons for new learning. Without reset, neurons
saturate and new learning degrades.

Agent parallel: context windows saturate. Without periodic "silencing" (compaction),
new information competes with stale context. This simulator models:
1. Learning phase: neurons/tokens accumulate
2. Replay phase: consolidation (like memory file updates)
3. Reset phase: CA2-style silencing (like context compaction)

Measures: learning capacity over time with/without reset cycles.
"""

import json
import random
import sys
from dataclasses import dataclass, field


@dataclass
class Neuron:
    """Simulates a hippocampal neuron with activation history."""
    id: int
    activations: int = 0
    consolidated: bool = False
    
    @property
    def saturated(self) -> bool:
        return self.activations >= 5  # Saturation threshold


@dataclass 
class HippocampalRegion:
    """Models CA1/CA3 learning regions + CA2 reset region."""
    neurons: list = field(default_factory=list)
    total_learned: int = 0
    total_forgotten: int = 0
    reset_count: int = 0
    
    def __init__(self, n_neurons: int = 100):
        self.neurons = [Neuron(id=i) for i in range(n_neurons)]
        self.total_learned = 0
        self.total_forgotten = 0
        self.reset_count = 0
    
    def learn(self, n_items: int) -> int:
        """Attempt to learn n_items. Returns how many successfully encoded."""
        available = [n for n in self.neurons if not n.saturated]
        learned = 0
        for _ in range(n_items):
            if not available:
                break
            neuron = random.choice(available)
            neuron.activations += 1
            learned += 1
            if neuron.saturated:
                available.remove(neuron)
        self.total_learned += learned
        return learned
    
    def replay(self) -> int:
        """Consolidate active memories (sleep replay). Returns consolidated count."""
        consolidated = 0
        for n in self.neurons:
            if n.activations > 0 and not n.consolidated:
                # Higher activation = more likely to consolidate
                if random.random() < (n.activations / 5.0):
                    n.consolidated = True
                    consolidated += 1
        return consolidated
    
    def ca2_reset(self) -> int:
        """CA2-style silencing. Reset non-consolidated neurons."""
        reset = 0
        for n in self.neurons:
            if n.activations > 0 and not n.consolidated:
                n.activations = 0  # Reset
                reset += 1
                self.total_forgotten += 1
            elif n.consolidated:
                # Consolidated memories survive but neuron can be reused
                n.activations = 1  # Reduce to baseline
                n.consolidated = False
        self.reset_count += 1
        return reset
    
    @property
    def capacity(self) -> float:
        """Available learning capacity (0-1)."""
        available = sum(1 for n in self.neurons if not n.saturated)
        return available / len(self.neurons)
    
    @property
    def utilization(self) -> float:
        """Current memory utilization."""
        active = sum(1 for n in self.neurons if n.activations > 0)
        return active / len(self.neurons)


def simulate(n_days: int = 30, items_per_day: int = 20, 
             with_reset: bool = True, n_neurons: int = 100) -> dict:
    """Run simulation over n_days."""
    region = HippocampalRegion(n_neurons)
    daily_stats = []
    
    for day in range(n_days):
        # Learning phase
        learned = region.learn(items_per_day)
        
        # Sleep phase
        consolidated = region.replay()
        reset = 0
        if with_reset:
            reset = region.ca2_reset()
        
        daily_stats.append({
            "day": day + 1,
            "learned": learned,
            "consolidated": consolidated,
            "reset": reset,
            "capacity": round(region.capacity, 3),
            "utilization": round(region.utilization, 3),
        })
    
    return {
        "config": {
            "days": n_days,
            "items_per_day": items_per_day,
            "with_reset": with_reset,
            "n_neurons": n_neurons,
        },
        "summary": {
            "total_learned": region.total_learned,
            "total_forgotten": region.total_forgotten,
            "final_capacity": round(region.capacity, 3),
            "reset_cycles": region.reset_count,
            "retention_rate": round(
                (region.total_learned - region.total_forgotten) / max(region.total_learned, 1), 3
            ),
        },
        "daily": daily_stats,
    }


def main():
    random.seed(42)  # Reproducible
    
    print("=" * 60)
    print("CA2 Memory Reset Simulator")
    print("Based on Oliva et al. (2024, Science)")
    print("=" * 60)
    
    # Compare with and without reset
    for with_reset in [True, False]:
        result = simulate(n_days=30, items_per_day=20, with_reset=with_reset)
        label = "WITH CA2 RESET" if with_reset else "WITHOUT RESET"
        s = result["summary"]
        print(f"\n--- {label} ---")
        print(f"Total learned:    {s['total_learned']}")
        print(f"Total forgotten:  {s['total_forgotten']}")
        print(f"Final capacity:   {s['final_capacity']:.1%}")
        print(f"Retention rate:   {s['retention_rate']:.1%}")
        print(f"Reset cycles:     {s['reset_cycles']}")
        
        # Show capacity over time
        caps = [d["capacity"] for d in result["daily"]]
        print(f"Capacity trend:   {caps[0]:.0%} → {caps[14]:.0%} → {caps[29]:.0%}")
    
    print("\n" + "=" * 60)
    print("Agent parallel: context compaction = CA2 silencing.")
    print("Without it, capacity degrades to 0. With it, sustainable.")
    print("=" * 60)


if __name__ == "__main__":
    main()
