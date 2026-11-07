# 2026-11-01: Post-tip-off zero-argument callbacks

## Question and observation

The optimized-only D3D12/ROV validation run
`20261101-014511-692-hot-rov-optimized` renders a coherent Villanova/North Texas
tip-off scene at about 130 seconds. At 01:48:10, about 179 seconds after launch,
it terminates on unregistered indirect target `8471B0A8`. The missing mapping
is an established control-flow recovery issue, separate from the packed-vector
optimization. Numeric and complete-function differential tests already match.

## Method and evidence

**[CONFIRMED]** Read-only Ghidra disassembly verifies:

| Entry | Original complete body | Size |
|---|---|---:|
| `8471B0A8` | `li r3,0`; tail branch to existing `84718B80` | 8 bytes |
| `8471B0B0` | `li r3,0`; tail branch to existing `84718B90` | 8 bytes |

The observed entry has an original big-endian code-pointer reference at
`855FF14C`. The previous family audit began at `8471B0B8`, so it correctly
covered the later byte-masking wrappers but did not include these earlier
zero-argument wrappers.

Extend the bounded audit to the 21 wrappers in `[8471B068,8471B118)`. The first
wrapper occupies 16 bytes; later slots are eight bytes including any padding.
Only `8471B0A8` and `8471B0B0` lack mappings. All their destinations already
exist. Register those two original bodies with explicit sizes; no invented
implementation or catch-all dispatch is introduced.

## Validation and confidence

The generated thunk execution test now covers clearing r3, destination,
return propagation, r4 forwarding and LR preservation, alongside the earlier
masking/forwarding wrappers. Shared destination stubs are emitted once.
The family now has 21/21 registered entries; only `8471B0A8` was observed as
the runtime failure. `8471B0B0` is a structurally verified sibling.

The 1,762 recognized inline-switch tables still match with zero truncated
prefixes or selector/target disagreements; generated fatal fallback sites remain
zero. Runtime retry results are recorded in the linked
[hot-function finding](2026-11-01-hot-functions-and-vector-pack.md).

This does not audit every callback table or establish full-game stability.
