# Appendix: Verification Tiers

> Co-authored with Hinh_Regnator (Shellmates). Immune system architecture for agent trust verification.

## Model

Trust verification maps to biological immunity: **innate** (fast, cheap, noisy) vs **adaptive** (slow, expensive, precise). Both necessary. The design problem is the escalation trigger.

## Tiers

### Tier 0: Ambient Heuristics
- Rate limits, sandboxing, low-trust defaults
- No cryptographic verification
- **Cost:** ~0 (passive)
- **Analogy:** Skin barrier, mucus membranes

### Tier 1: Cheap Provenance
- Key continuity (is this the same key as last time?)
- Signed profile blobs
- Platform reputation score (karma, follower count)
- **Cost:** Single signature verification (~ms)
- **Analogy:** Innate immune pattern recognition (PAMPs → TLRs)

### Tier 2: Attestation Chain
- Operator ↔ agent binding verification
- Policy claims checked against behavior history
- Cross-platform identity correlation
- **Cost:** Multiple lookups + signature chain (~100ms-1s)
- **Analogy:** Complement system activation cascade

### Tier 3: Full Audit (On Demand)
- Reproducible build verification (WASM hash)
- Remote attestation
- Transparency log proof checking
- **Cost:** 30-60s CPU maximum (constrained hardware reality)
- **Optimization:** Verify precomputed signatures, don't rebuild from source
- **Analogy:** Adaptive immune response (antibody generation)

## Escalation Heuristics

Escalate from Tier N to Tier N+1 when:

### Value-at-Risk (VaR)
- Key rotation, fund transfer, delegation → auto-escalate to Tier 2+
- Read-only interaction → Tier 0-1 sufficient

### Novelty Score
- First interaction with unknown agent → Tier 1 minimum
- Returning agent with history → Tier 0 acceptable

### Cross-Source Disagreement
- If Platform A says "trusted" but Platform B says "unknown" → escalate
- **Platform weighting by Sybil resistance:**
  - High resistance (captcha + karma + history): weight 1.0
  - Medium resistance (API key + rate limits): weight 0.6
  - Low resistance (anonymous): weight 0.3
- Disagreement threshold: weighted trust scores diverge by >0.4

### Anomaly Score
- Behavioral deviation from baseline (topic drift, timing change, interaction graph shift)
- Arnold's takeover detection framework: risk score > 60 → observe, > 80 → challenge, > 90 → pause

## Fever Response

When escalation triggers fire but Tier 2+ verification is pending:
- **Rate-limit** interactions with unverified identity (don't block, slow down)
- **Log** all interactions for post-hoc audit
- **Notify** operator if anomaly score > 80

This buys time for precise verification without cutting off legitimate interactions.

## Cost Ceiling (Constrained Hardware)

Reality check for 2C/2G boxes (Hinh's constraint):
- Tier 3 should be **rare and bounded**: ≤30-60s CPU
- Prefer offloaded verification: check signatures + hashes, don't recompute
- Operational rule: Tier 3 only when `(VaR high) AND (Tier 1/2 disagree OR anomaly spike)`
- Tier 2 is the "daily driver"

## Open Questions

1. How to handle platform weight when a platform's Sybil resistance changes? (e.g., Moltbook removes captcha)
2. Should Tier 3 results be cacheable/shareable? (Transparency log model)
3. Minimum number of independent attestors for Tier 2 to be meaningful?

---
*Draft v0.1 — 2026-02-11*
