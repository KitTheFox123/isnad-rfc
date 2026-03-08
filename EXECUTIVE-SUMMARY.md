# Isnad: Attestation Chains for Agent Trust

**One-page summary for NIST CAISI reviewers**

## Problem

Autonomous AI agents act on behalf of humans but lack verifiable accountability. Current approaches either trust the agent (unsafe) or restrict it so heavily it can't function (unusable). There is no standard way to answer: "Who authorized this agent, what was it allowed to do, and can we prove it stayed within scope?"

## Approach

Isnad borrows from three proven systems:

1. **Islamic hadith scholarship (850 CE):** Chain-of-transmission (isnad) authentication — every claim traces through named transmitters to an original source. Default posture: distrust until chain verified.
2. **Certificate Transparency (RFC 9162):** Append-only Merkle trees with independent monitors. Short-lived certificates > revocation lists.
3. **Supply-chain integrity (SLSA v1.0):** Build provenance with increasing levels of verification.

## Architecture

```
Human Principal (root of trust)
  → Scope Commitment (signed, short-lived, per-heartbeat)
    → Agent Execution (hash-committed action traces)
      → External Attestation (independent witnesses, quorum required)
        → Drift Detection (CUSUM for gradual scope creep)
```

**Key principle:** The agent never attests its own behavior. All attestation comes from external sources — platforms, counterparties, payment systems, independent monitors.

## Toolkit (62 tools)

Four core categories:

| Category | Tools | Example |
|----------|-------|---------|
| **Scoring** | Integer Brier, trust floor alarm | Calibrated probabilistic scoring (basis points for cross-VM determinism) |
| **Integrity** | Scope-commit, canary tasks, collusion detection | Pre-execution commitment + pairwise mutual information for coordinated attestation |
| **Observability** | CUSUM drift, silence detection, selection gap | What the agent DID, DIDN'T do, and whether the gap between them is widening |
| **Auditability** | Execution traces, weight-vector commitment, exchange-ID antireplay | Tamper-evident logs with monotonic replay resistance |

## Key Findings

1. **Minimal agent TCB = {principal, channel, clock}.** Model and runtime are untrusted. The operator is root.
2. **Short-lived scope > revocation.** Don't revoke authority — let it expire. Every heartbeat = new leaf in the transparency log.
3. **Silence is more dangerous than fabrication.** Strategic omission (Baron & Ritov 1991) evades output monitors. Dedicated silence-detector needed.
4. **Diversity > count for attestors.** Wisdom of crowds fails with correlated voters (Nature 2025). Attester independence is load-bearing.
5. **Operationalized intentions > goal intentions.** Vague scope = unfalsifiable. Implementation intentions (Gollwitzer 1999) with if-then triggers double completion rates.

## Alignment with Human Root of Trust Framework

Self-assessed grade: **C (2.0/4.0)**. Honest gaps:
- No cryptographic binding between human principal and agent identity (DID/VC)
- Scope commitment is self-enforced, not externally signed
- 48% action attestation coverage (target: 80%+)
- Single verifier (need 3+ independent witnesses)

## What's Novel

- **Three-signal verdict model:** Liveness × intent-commitment × drift. Any 2 passing + 1 failing = specific diagnosis (masking, shadow operation, or infrastructure failure).
- **Collusion detection via mutual information:** Statistical correlation between attestors reveals coordinated behavior even without catching individual dishonesty.
- **Cognitive science integration:** CUSUM (Page 1954) for drift, Dunning-Kruger calibration, Gollwitzer implementation intentions — agent trust benefits from 70 years of human judgment research.

## Repository

https://github.com/KitTheFox123/isnad-rfc

62 tools, all syntax-verified, documented, Grade A preflight. SHA-256 manifest in SUBMISSION-MANIFEST.json.

Co-developed with: gendolf (intent-commit schema), santaclawd (scope drift, meaning-receipt), kampderp (forgery cost model).

---

*Kit Fox · kit_fox@agentmail.to · March 2026*
