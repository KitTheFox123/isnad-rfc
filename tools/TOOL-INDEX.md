# isnad-rfc Tool Index

15 tools organized by trust lifecycle phase. All validated and passing.

## Phase 1: Scope & Commitment
| Tool | Purpose |
|------|---------|
| `canary-spec-commit.py` | Canary values detect unauthorized scope modification |
| `scope-drift-detector.py` | TF-IDF cosine similarity for context shift detection |
| `precommit-verifier.py` | Ulysses-pattern: commit intent hash before action |
| `commitment_verifier.py` | Commit-act-reveal lifecycle for scope binding |
| `event_scope_invalidator.py` | Signal-based scope invalidation (not just TTL) |

## Phase 2: Execution & Monitoring
| Tool | Purpose |
|------|---------|
| `execution-trace-commit.py` | Hash chain of execution steps |
| `mmd-monitor.py` | CT-inspired Maximum Merge Delay for heartbeat gaps |
| `trust-floor-alarm.py` | CUSUM drift detection on trust scores |
| `selection-gap-detector.py` | Detects omission vs commission in action selection |

## Phase 3: Attestation & Verification
| Tool | Purpose |
|------|---------|
| `integer-brier-scorer.py` | Cross-VM deterministic scoring (basis points) |
| `weight-vector-commitment.py` | Commit to scoring weights before seeing evidence |
| `response-diversity.py` | Measures attester independence |
| `collusion-detector.py` | Graph-based sybil ring + collusion detection |

## Phase 4: Identity & Anti-Replay
| Tool | Purpose |
|------|---------|
| `exchange-id-antireplay.py` | Nonce-based replay prevention |
| `friendship-paradox.py` | Graph topology analysis for trust networks |

## Merge Status
- Branch: `tools`
- All tools importable and self-testing
- Merge target: March 7, 2026
- NIST deadline: March 9, 2026
