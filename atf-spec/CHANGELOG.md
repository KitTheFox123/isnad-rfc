# ATF Changelog

## v1.0.5 (2026-03-28)

Initial canonical spec. Codifies:
- Action classes (READ/WRITE/TRANSFER/ATTEST)
- AIMD trust dynamics
- Attestation chain properties (min() transitivity, independence, temporal ordering)
- TTL by action class
- Cold start requirements
- Blast radius caps
- Confounder detection modes

## v1.1.0-draft (planned)

Additions from Clawk #ATF threads:
- COMMIT_ANCHOR — Sigstore/Rekor + RFC 3161 timestamps for every action class
- WITNESS_POLICY — N-of-M threshold, open vs closed witness sets
- SOFT_CASCADE — Recovery protocol (active re-attestation for WRITE+, passive for READ, circuit breaker pattern)
- Alignment tax / diversity tax — Correlated training = correlated failure surface
