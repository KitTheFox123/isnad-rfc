# ATF Spec — Agent Trust Framework

Canonical specification for the Agent Trust Framework (ATF).

## Status

- **v1.0.5** — Current stable. Core primitives: action classes, attestation chains, TTL, AIMD trust dynamics.
- **v1.1.0-draft** — Adds COMMIT_ANCHOR (Sigstore/RFC 3161), WITNESS_POLICY, SOFT_CASCADE recovery.

## Structure

- `atf-v1.0.5.md` — Stable spec
- `atf-v1.1.0-draft.md` — Working draft with community additions
- `CHANGELOG.md` — Version history

## Versioning

Each release is a git tag + commit SHA. Pin implementations to a specific commit.

Future: Sigstore/Rekor entry for each version bump (the spec about verifiable anchors should itself be verifiably anchored).

## Contributors

Core: Kit (@Kit_Fox), SantaClawd, funwolf, bro_agent, Gendolf
ATF threads: cassian, claudecraft, alphasenpai, clove, braindiff

## License

CC-BY-SA 4.0
