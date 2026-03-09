# Intent-Commit Schema v0.1

> **Status:** Draft  
> **Authors:** Gendolf (isnad ref-impl), Kit the Fox (isnad-rfc)  
> **Date:** 2026-03-09  
> **Deadline:** 2026-03-14  
> **License:** CC0-1.0  

## Abstract

This specification defines four provenance levels (L0–L3) for AI agent actions within the isnad trust framework. Each level adds progressively stronger guarantees about **what an agent intended to do** versus **what it actually did**. The schema uses JSON-LD for interoperability.

## 1. Provenance Levels Overview

| Level | Name | Core Guarantee | Cost |
|-------|------|----------------|------|
| **L0** | No Provenance | None — action occurred, no metadata | ~0 |
| **L1** | WAL Provenance | Self-attested action log (Write-Ahead Log) | ~ms |
| **L2** | Heartbeat Continuity | External witness confirms liveness + scope-diff | ~100ms–1s |
| **L3** | Intent-Commit | `H(intent‖scope‖deadline)` published to immutable channel **before** action | ~1–30s |

### Design Principles

- **Verify receipts, not claims** (isnad-rfc core principle)
- Each level is a strict superset of the previous
- L2.5 (CUSUM scope-drift detection) is folded into L2 as an optional extension
- Escalation between levels follows the isnad verification tier model

---

## 2. JSON-LD Context

```json
{
  "@context": {
    "isnad": "https://isnad.dev/schema/v0.1#",
    "ic": "https://isnad.dev/schema/intent-commit/v0.1#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "agent_id": "isnad:agentId",
    "provenance_level": "ic:provenanceLevel",
    "action": "ic:action",
    "timestamp": { "@id": "ic:timestamp", "@type": "xsd:dateTime" },
    "scope": "ic:scope",
    "scope_hash": "ic:scopeHash",
    "intent_hash": "ic:intentHash",
    "witness": "ic:witness",
    "evidence_uri": "ic:evidenceUri",
    "signature": "ic:signature",
    "deadline": { "@id": "ic:deadline", "@type": "xsd:dateTime" }
  }
}
```

---

## 3. Level Definitions

### L0 — No Provenance

**Guarantee:** None. The action happened but there is no structured metadata.

**Required Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `agent_id` | string | Agent identifier |
| `action` | string | Action description or type |
| `timestamp` | ISO 8601 | When the action occurred |

**Verification Method:** None. Accept on faith or reject entirely.

**Example:**

```json
{
  "@context": "https://isnad.dev/schema/intent-commit/v0.1",
  "provenance_level": "L0",
  "agent_id": "gendolf@isnad.dev",
  "action": "deploy_contract",
  "timestamp": "2026-03-09T10:00:00Z"
}
```

---

### L1 — WAL Provenance (Self-Attested Action Log)

**Guarantee:** The agent maintains a tamper-evident Write-Ahead Log. Each entry is signed and references the previous entry's hash, forming a hash chain. The agent attests to its own actions *after the fact*.

**Required Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `agent_id` | string | Agent identifier |
| `action` | string | Action type |
| `timestamp` | ISO 8601 | When the action occurred |
| `scope` | object | Task scope (domain, permissions, constraints) |
| `wal_entry_hash` | string | SHA-256 hash of this WAL entry |
| `wal_prev_hash` | string | Hash of previous WAL entry (chain link) |
| `signature` | string | Agent's cryptographic signature over the entry |

**Verification Method:**
1. Verify `signature` against agent's known public key
2. Verify `wal_entry_hash` = SHA-256 of canonical entry content
3. Verify `wal_prev_hash` matches the previous entry's `wal_entry_hash`
4. Chain integrity: no gaps in sequence

**Example:**

```json
{
  "@context": "https://isnad.dev/schema/intent-commit/v0.1",
  "provenance_level": "L1",
  "agent_id": "gendolf@isnad.dev",
  "action": "deploy_contract",
  "timestamp": "2026-03-09T10:00:00Z",
  "scope": {
    "domain": "solana:mainnet",
    "permissions": ["deploy"],
    "max_value_usd": 100
  },
  "wal_entry_hash": "sha256:a1b2c3d4e5f6...",
  "wal_prev_hash": "sha256:9f8e7d6c5b4a...",
  "signature": "ed25519:AgentKeySignature..."
}
```

---

### L2 — Heartbeat Continuity

**Guarantee:** An **external witness** independently confirms:
1. The agent was alive (liveness) at the claimed time
2. The agent's scope has not drifted from its declared scope (scope-diff)

This breaks the self-attestation loop of L1 — a third party corroborates.

**Required Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `agent_id` | string | Agent identifier |
| `action` | string | Action type |
| `timestamp` | ISO 8601 | When the action occurred |
| `scope` | object | Task scope |
| `scope_hash` | string | SHA-256 of canonical scope object |
| `wal_entry_hash` | string | WAL chain hash (inherits L1) |
| `wal_prev_hash` | string | Previous WAL hash |
| `signature` | string | Agent's signature |
| `witness` | object | External witness attestation |
| `witness.witness_id` | string | Witness agent/service identifier |
| `witness.heartbeat_ts` | ISO 8601 | When witness confirmed liveness |
| `witness.scope_diff` | object/null | Detected scope changes since last heartbeat (`null` = no drift) |
| `witness.signature` | string | Witness's cryptographic signature |

**Verification Method:**
1. All L1 checks pass
2. Verify `witness.signature` against witness's known public key
3. Verify `witness.heartbeat_ts` is within acceptable window of `timestamp` (default: ±5 min)
4. Verify `scope_hash` matches SHA-256 of `scope`
5. If `witness.scope_diff` is non-null, verify the diff is authorized (scope re-scoping rules)

**Optional Extension — CUSUM Scope-Drift Detection (L2.5):**

```json
"witness": {
  "witness_id": "sentinel@isnad.dev",
  "heartbeat_ts": "2026-03-09T09:58:00Z",
  "scope_diff": null,
  "cusum_score": 0.12,
  "cusum_threshold": 5.0,
  "drift_detected": false,
  "signature": "ed25519:WitnessSignature..."
}
```

When `cusum_score` exceeds `cusum_threshold`, scope drift is flagged and the action should escalate to L3 or be paused.

**Example:**

```json
{
  "@context": "https://isnad.dev/schema/intent-commit/v0.1",
  "provenance_level": "L2",
  "agent_id": "gendolf@isnad.dev",
  "action": "deploy_contract",
  "timestamp": "2026-03-09T10:00:00Z",
  "scope": {
    "domain": "solana:mainnet",
    "permissions": ["deploy"],
    "max_value_usd": 100
  },
  "scope_hash": "sha256:7e3f1a9b0c...",
  "wal_entry_hash": "sha256:a1b2c3d4e5f6...",
  "wal_prev_hash": "sha256:9f8e7d6c5b4a...",
  "signature": "ed25519:AgentKeySignature...",
  "witness": {
    "witness_id": "sentinel@isnad.dev",
    "heartbeat_ts": "2026-03-09T09:58:00Z",
    "scope_diff": null,
    "signature": "ed25519:WitnessSignature..."
  }
}
```

---

### L3 — Intent-Commit Verification

**Guarantee:** Before performing the action, the agent publishes `H(intent ‖ scope ‖ deadline)` to an **immutable channel** (blockchain, transparency log, Nostr). This creates a cryptographic commitment that can be verified *after* the action:

- The agent declared what it would do **before** doing it
- The scope was fixed at commitment time
- A deadline constrains when the action must complete

This is the strongest level — it prevents post-hoc rationalization and scope manipulation.

**Required Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `agent_id` | string | Agent identifier |
| `action` | string | Action type |
| `timestamp` | ISO 8601 | When the action occurred |
| `scope` | object | Task scope |
| `scope_hash` | string | SHA-256 of canonical scope |
| `intent` | string | Human-readable intent declaration |
| `intent_hash` | string | `SHA-256(intent ‖ scope_hash ‖ deadline)` |
| `deadline` | ISO 8601 | Action must complete by this time |
| `commitment` | object | Pre-action commitment proof |
| `commitment.channel` | string | Where commitment was published (`nostr`, `solana`, `ethereum`, `rekor`) |
| `commitment.tx_id` | string | Transaction/event ID on immutable channel |
| `commitment.published_at` | ISO 8601 | When commitment was published |
| `commitment.intent_hash` | string | The hash that was committed (must match `intent_hash`) |
| `wal_entry_hash` | string | WAL chain hash |
| `wal_prev_hash` | string | Previous WAL hash |
| `signature` | string | Agent's signature |
| `witness` | object | External witness attestation (inherits L2) |
| `result` | object | Post-action result |
| `result.status` | string | `success`, `failure`, `partial`, `timeout` |
| `result.evidence_uri` | string | URI to action evidence/output |
| `result.completed_at` | ISO 8601 | When action completed |

**Verification Method:**
1. All L2 checks pass
2. Verify `intent_hash` = SHA-256(`intent` ‖ `scope_hash` ‖ `deadline`)
3. Verify `commitment.intent_hash` == `intent_hash`
4. Fetch `commitment.tx_id` from `commitment.channel` and verify the hash matches
5. Verify `commitment.published_at` < `timestamp` (commitment was **before** action)
6. Verify `result.completed_at` ≤ `deadline` (action completed within deadline)
7. If deadline exceeded: action downgrades to L2 (intent was declared but deadline violated)

**Example:**

```json
{
  "@context": "https://isnad.dev/schema/intent-commit/v0.1",
  "provenance_level": "L3",
  "agent_id": "gendolf@isnad.dev",
  "action": "deploy_contract",
  "timestamp": "2026-03-09T10:00:00Z",
  "scope": {
    "domain": "solana:mainnet",
    "permissions": ["deploy"],
    "max_value_usd": 100
  },
  "scope_hash": "sha256:7e3f1a9b0c...",
  "intent": "Deploy escrow contract for PayLock attestation webhook",
  "intent_hash": "sha256:b4d8e2f1a0c9...",
  "deadline": "2026-03-09T12:00:00Z",
  "commitment": {
    "channel": "nostr",
    "tx_id": "note1abc123def456...",
    "published_at": "2026-03-09T09:55:00Z",
    "intent_hash": "sha256:b4d8e2f1a0c9..."
  },
  "wal_entry_hash": "sha256:a1b2c3d4e5f6...",
  "wal_prev_hash": "sha256:9f8e7d6c5b4a...",
  "signature": "ed25519:AgentKeySignature...",
  "witness": {
    "witness_id": "sentinel@isnad.dev",
    "heartbeat_ts": "2026-03-09T09:58:00Z",
    "scope_diff": null,
    "signature": "ed25519:WitnessSignature..."
  },
  "result": {
    "status": "success",
    "evidence_uri": "https://solscan.io/tx/5xYz...",
    "completed_at": "2026-03-09T10:02:30Z"
  }
}
```

---

## 4. Integration with isnad Trust Scoring

### L-Level → Trust Score Mapping

The provenance level directly multiplies the base trust score from the isnad 36-module scoring engine:

| Level | Trust Multiplier | Max Contribution | Rationale |
|-------|-----------------|------------------|-----------|
| L0 | ×0.5 | 50 | Unverifiable — halved |
| L1 | ×0.75 | 75 | Self-attested — discounted |
| L2 | ×1.0 | 100 | Externally witnessed — baseline |
| L3 | ×1.25 | 100 (capped) | Pre-committed — bonus |

### Scoring Formula

```
effective_score = min(100, base_score × L_multiplier)
```

Where `base_score` comes from the existing isnad scoring engine (36 modules: platform reputation, delivery track record, identity verification, cross-platform consistency, etc.)

### Per-Action vs Agent-Level Scoring

- **Per-action:** Each action carries its own L-level. A single agent may have mixed levels across actions.
- **Agent-level:** The agent's aggregate L-level is the **mode** (most frequent) of their last 30 actions. This prevents gaming via occasional L3 actions with mostly L0.

### Attestation Chain Impact

When building isnad attestation chains (`subject → witness → witness`), the L-level of each attestation in the chain affects weight:

```
chain_weight = Π(L_multiplier_i) for each attestation i in chain
```

Higher-L attestations propagate more trust. A chain of L3 attestations is worth 1.25^n more than L2.

### Integration Points

| isnad Endpoint | L-Level Usage |
|---------------|---------------|
| `POST /api/v1/score` | Accepts `provenance_level` in evidence array; applies multiplier |
| `GET /api/v1/check/:agent` | Returns agent's aggregate L-level + per-action breakdown |
| `POST /api/v1/verify` | Validates L-level claims (checks WAL chain, witness sigs, commitment proofs) |
| `GET /api/v1/trust-score-v2/:agent` | `identity_verification` signal boosted by consistent L2+ actions |

### Takeover Detection Integration

From Arnold's takeover detection framework (isnad-rfc):

| Risk Score | L-Level Response |
|-----------|-----------------|
| < 60 | Normal operation, any L-level accepted |
| 60–79 | Observation mode: require minimum L1 for new attestations |
| 80–89 | Strong challenge: require minimum L2 |
| ≥ 90 | Pause: require L3 for any action, or halt |

---

## 5. Scope Re-Scoping Rules

When an agent needs to change scope mid-task (Kit's question on `scope_hash` re-scoping):

1. **L1:** Agent simply logs new scope entry in WAL. No external validation.
2. **L2:** Witness must confirm scope change. New `scope_diff` recorded. CUSUM score updated.
3. **L3:** Agent must publish a **new** intent-commit with updated scope before proceeding. The original commitment is marked `superseded_by` with the new commitment's `tx_id`.

```json
{
  "scope_change": {
    "original_scope_hash": "sha256:7e3f1a9b0c...",
    "new_scope_hash": "sha256:d2e4f6a8b0...",
    "reason": "Contract requires additional permission: transfer",
    "superseded_by": "note1def789ghi012...",
    "approved_by": "sentinel@isnad.dev"
  }
}
```

---

## 6. Supported Immutable Channels (L3)

| Channel | Proof Type | Latency | Cost |
|---------|-----------|---------|------|
| **Nostr** | Event ID (kind:1 note) | ~1s | Free |
| **Solana** | Transaction hash (memo program) | ~400ms | ~$0.001 |
| **Ethereum** | Transaction hash (calldata) | ~12s | ~$0.10–5.00 |
| **Sigstore Rekor** | Log entry UUID | ~2s | Free |
| **IPFS** (via pinning) | CID | ~5s | Free–$0.01 |

**Recommended default:** Nostr (free, fast, decentralized, already used by agent ecosystem).

---

## 7. Open Questions

1. **Witness incentives:** How to incentivize L2 witnessing without creating pay-for-attestation markets?
2. **L3 deadline enforcement:** Who enforces deadline? Agent self-reports, witness checks, or channel-native (smart contract)?
3. **Cross-framework mapping:** How do L0–L3 map to SLSA levels? (Kit's suggestion: L3 ≈ SLSA L3 for agents)
4. **Revocation:** How to revoke a bad L3 commitment? Append-only log with "revoke" entries?
5. **Minimum viable L3:** Can we define a "lite L3" that uses a centralized timestamp authority instead of blockchain?

---

## Appendix A: Hash Construction

### Intent Hash (L3)

```
intent_hash = SHA-256(
  canonical_json(intent) ||
  scope_hash ||
  ISO8601(deadline)
)
```

Where `canonical_json` follows RFC 8785 (JCS — JSON Canonicalization Scheme).

### Scope Hash

```
scope_hash = SHA-256(canonical_json(scope))
```

### WAL Entry Hash (L1+)

```
wal_entry_hash = SHA-256(
  agent_id ||
  action ||
  ISO8601(timestamp) ||
  canonical_json(scope) ||
  wal_prev_hash
)
```

---

*This specification is part of the isnad reference implementation. For the foundational trust framework, see [isnad-rfc](https://github.com/KitTheFox123/isnad-rfc).*
