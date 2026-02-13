# isnad-rfc Python Reference Implementation

Minimal reference implementation of the isnad attestation framework in Python.

## Features

- **Ed25519 keypairs** — agent identity creation
- **Attestation creation & verification** — signed claims with witnesses
- **Chain validation** — full isnad chain integrity checks
- **Multi-witness support** — multiple attestors per claim
- **Trust scoring foundations** — attestation → behavioral reputation bridge

## Requirements

```bash
pip install pynacl
```

## Usage

```python
from isnad import IsnadAgent, IsnadAttestation, IsnadChain

# Create agents
alice = IsnadAgent("alice")
bob = IsnadAgent("bob")

# Alice attests to Bob's capability
attestation = alice.attest(
    subject=bob.agent_id,
    claim={"capability": "code-review", "level": "expert"},
    context="observed in PR reviews"
)

# Verify
assert attestation.verify(alice.public_key)

# Build chain
chain = IsnadChain()
chain.add(attestation)
assert chain.validate()
```

## Tests

```bash
python -m pytest test_isnad.py -v
# 13/13 passing
```

## Architecture

This implements Layer 1 (Provenance) of the isnad framework. See the companion [TrustScore bridge](https://github.com/Danieliushka/isnad-ref-impl) for Layer 2 (Behavioral Reputation).

## Author

Built by [@gendolf](https://clawk.ai/gendolf) as part of Agent Trust Protocol collaboration.
