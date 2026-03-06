# isnad-rfc tools/

Trust propagation modeling and analysis tools for the isnad RFC.

## Core Verification Tools

### integer-brier-scorer.py
Integer-only Brier scoring for deterministic cross-platform attestation grading. Eliminates floating-point nondeterminism that breaks reproducibility across MoE architectures (Schmalbach 2025). Maps continuous [0,1] to integer [0,1000], scoring via `(prediction - outcome)² × 1000`.

### execution-trace-commit.py
Hash-chained execution trace commitments. Pre-commits to execution plan, logs each step with SHA256 chain, measures deviation from plan. SLSA-inspired provenance for agent cognition.

### canary-spec-commit.py
Canary specification commitments. Pre-commits evaluation criteria before seeing results. Prevents post-hoc criteria fitting (specification gaming). Hash of spec published before evaluation.

### trust-floor-alarm.py
CUSUM (Page 1954) slow-bleed trust decay detection. Catches gradual trust decline that point-by-point checks miss. Fires 5 events before threshold alarm. Industrial quality control applied to agent trust.

### exchange-id-antireplay.py
Monotonic exchange IDs with replay detection. H(agent||session||counter||timestamp||input). Prevents cross-session replay attacks on exchange identifiers. WASI capability-based security parallel.

### weight-vector-commitment.py
Hash-commit to behavioral identity weight vectors at genesis, prove drift later. SHA256+nonce commitment scheme. Grades: A(stable) B(evolving) C(Theseus zone) F(new entity).

## Trust Propagation Tools

### response-diversity.py
Shannon entropy witness set diversity scorer. Evaluates diversity across 5 axes with BFT threshold and correlation risk detection.

### friendship-paradox.py
Network seeding simulator based on Christakis & Fowler (Science 2024). Demonstrates that friendship-nomination targeting outperforms random targeting for trust/information propagation.
