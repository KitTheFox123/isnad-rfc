# Isnad RFC — Submission Review Summary

*Generated 2026-03-08 01:09 UTC | Branch: main | 1fc22599b2244ab710eb897d2418112ef7f764e0 Generate *

## Overview

- **Total tools:** 60
- **Total lines:** 12,260
- **Categories:** 5

## Analysis & Simulation (9 tools)

| Tool | Lines | Description |
|------|-------|-------------|
| `attestor-selection-sim.py` | 186 | attestor-selection-sim.py — Optimal Attestor Selection via Secretary Problem |
| `memory-reset-simulator.py` | 180 | memory-reset-simulator.py — Models CA2-inspired memory reset for agent contexts. |
| `nist-preflight.py` | 189 | nist-preflight.py — Pre-submission validator for NIST CAISI package. |
| `nist-submission-readme.py` | 96 | Generate a human-readable README for NIST CAISI submission. |
| `scope-vote-simulator.py` | 222 | scope-vote-simulator.py — Byzantine scope-violation voting simulator |
| `submission-manifest.py` | 66 | Generate NIST CAISI submission manifest with integrity hashes. |
| `submission-preflight.py` | 224 | submission-preflight.py — NIST CAISI Submission Package Validator |
| `submission-review.py` | 157 | NIST CAISI Submission Review Checklist |
| `thread-quality-bootstrap.py` | 304 | thread-quality-bootstrap.py — BCa Bootstrap Analysis for Pre-Registered Study |

## Identity & Provenance (3 tools)

| Tool | Lines | Description |
|------|-------|-------------|
| `exchange-id-antireplay.py` | 187 | exchange-id-antireplay.py — Monotonic exchange IDs with replay detection. |
| `gossip-failure-detector.py` | 251 | gossip-failure-detector.py — Gossip-based agent liveness detection. |
| `scope-gossip-sim.py` | 179 | scope-gossip-sim.py — Gossip protocol for agent scope verification |

## Other (1 tools)

| Tool | Lines | Description |
|------|-------|-------------|
| `submission-readiness.py` | 156 | NIST CAISI Submission Readiness Checker. |

## Scope & Authorization (22 tools)

| Tool | Lines | Description |
|------|-------|-------------|
| `canary-spec-commit.py` | 172 | canary-spec-commit.py — Pre-committed canary probes for circuit breaker half-ope |
| `commitment-window-analyzer.py` | 293 | commitment-window-analyzer.py — Analyze agent commitment windows for optimal tru |
| `commitment_verifier.py` | 182 | commitment_verifier.py — Verify scope commitment binding. |
| `credible_commitment_analyzer.py` | 238 | credible_commitment_analyzer.py — Tool #20 for isnad-rfc. |
| `intent-commit.py` | 217 | intent-commit.py — Intent commitment before execution (L2→L3 bridge). |
| `intention-overwrite-detector.py` | 403 | intention-overwrite-detector.py — Detect incomplete intention deactivation in ag |
| `mmd-monitor.py` | 324 | mmd-monitor.py — Maximum Merge Delay monitor for agent heartbeats. |
| `precommit-verifier.py` | 153 | precommit-verifier.py — Verify pre-commitment hashes against actual outputs. |
| `procedure_commitment_auditor.py` | 125 | procedure_commitment_auditor.py — Audit scope files for procedural vs outcome co |
| `proximity_drift_scorer.py` | 209 | proximity_drift_scorer.py — PATE-inspired proximity-aware scope drift scoring. |
| `renewal-or-die.py` | 236 | renewal-or-die.py — Short-Lived Scope Certificate Simulator |
| `safety-liveness-classifier.py` | 231 | safety-liveness-classifier.py — Classify agent accountability properties |
| `scope-drift-detector.py` | 234 | scope-drift-detector.py — Detect gradual scope drift using CUSUM control charts. |
| `scope-expiry-enforcer.py` | 197 | scope-expiry-enforcer.py — Enforce short-lived scope certificates for agent dele |
| `scope-expiry-monitor.py` | 185 | scope-expiry-monitor.py — Detect prospective memory commission errors in agent s |
| `scope-freshness-monitor.py` | 160 | scope-freshness-monitor.py - Monitor agent scope certificate freshness. |
| `scope-transparency-log.py` | 230 | scope-transparency-log.py — CT-inspired append-only scope log for agent delegati |
| `selection-gap-detector.py` | 174 | selection-gap-detector.py — Quantify selection bias in agent decision-making. |
| `semantic_changepoint.py` | 341 | semantic_changepoint.py — Semantic changepoint detection for agent scope logs. |
| `three-signal-verdict.py` | 227 | three-signal-verdict.py — Three-Signal Agent Health Monitor |
| `toctou-scope-detector.py` | 216 | toctou-scope-detector.py — Detect Time-of-Check-to-Time-of-Use gaps in agent sco |
| `weight-vector-commitment.py` | 233 | weight-vector-commitment.py — Cryptographic commitment to behavioral identity we |

## Trust & Attestation (25 tools)

| Tool | Lines | Description |
|------|-------|-------------|
| `attestation_loafing_detector.py` | 208 | attestation_loafing_detector.py — Detect social loafing in multi-agent attestati |
| `collusion-detector.py` | 273 | collusion-detector.py — Detect coordinated attestation via mutual information. |
| `event_scope_invalidator.py` | 185 | event_scope_invalidator.py — Event-driven scope invalidation for agent delegatio |
| `execution-trace-commit.py` | 219 | execution-trace-commit.py — Execution trace commitment for scoring oracle attest |
| `friendship-paradox.py` | 157 | friendship-paradox.py — Friendship paradox network seeding simulator. |
| `generate-review-summary.py` | 118 | generate-review-summary.py — NIST CAISI Review Summary Generator |
| `integer-brier-scorer.py` | 194 | integer-brier-scorer.py — Brier scoring in integer arithmetic for cross-VM deter |
| `liveness-renewal.py` | 237 | liveness-renewal.py — Active Renewal as Liveness Attestation |
| `merge-changelog.py` | 105 | Generate merge changelog for isnad-rfc tools branch → main. |
| `meta_attestation_validator.py` | 155 | meta_attestation_validator.py — Detect garbage-in-garbage-out in aggregated atte |
| `nist-review-checklist.py` | 161 | nist-review-checklist.py — NIST CAISI Submission Review Checklist |
| `pre-submit-validator.py` | 169 | pre-submit-validator.py — NIST CAISI Pre-Submission Validator |
| `repetition_truth_detector.py` | 217 | repetition_truth_detector.py — Detect illusory truth patterns in attestation net |
| `response-diversity.py` | 146 | response-diversity.py — Score attestation/witness diversity across agent network |
| `rfi-response-formatter.py` | 222 | rfi-response-formatter.py — Format isnad-rfc tools + research into NIST CAISI RF |
| `scope-cert-issuer.py` | 129 | scope-cert-issuer.py — Short-lived scope certificate issuer for agent delegation |
| `signal-freshness-decay.py` | 197 | signal-freshness-decay.py — Trust Signal Freshness Decay Model |
| `signed-halt-attestation.py` | 225 | signed-halt-attestation.py — Dead man's switch for agent accountability. |
| `sleeper_effect_detector.py` | 199 | sleeper_effect_detector.py — Detect sleeper effect patterns in attestation trust |
| `trust-decay-fitter.py` | 175 | trust-decay-fitter.py — Fit trust decay curves to attestation data. |
| `trust-decay-model.py` | 178 | trust-decay-model.py — Ebbinghaus-inspired trust decay for attestations |
| `trust-floor-alarm.py` | 202 | trust-floor-alarm.py — Detect silent trust decay before it hits the floor. |
| `trust-freshness-decay.py` | 244 | trust-freshness-decay.py — Ebbinghaus-inspired trust decay for attestations |
| `witness-network-sim.py` | 211 | witness-network-sim.py — Simulates witness network consistency guarantees. |
| `witness_cosigner.py` | 357 | witness_cosigner.py — CoSi-inspired witness cosigning simulator for agent attest |

## Key Documents

- **NIST-SUBMISSION.md** — 4,618 bytes
- **README.md** — 893 bytes
- **SUBMISSION-MANIFEST.json** — 7,733 bytes
- **tools/PRE-MERGE-VALIDATION.md** — 1,815 bytes
