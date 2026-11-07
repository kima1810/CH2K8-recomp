# 2026-10-31: Gameplay startup missing callbacks

Follow-up: the next attempt reaches the arena introduction, then a missing
callback in a different table. See the [arena-introduction finding](2026-10-31-arena-intro-callbacks.md).

## Question

Why does the user-confirmed menu build black-screen and terminate when gameplay starts?

## Method

- Inspected the user's latest local runtime log, `ch2k8_004.log`, and its
  corresponding Windows Application Error record.
- Compared the reported guest target with the generated registration table.
- Inspected the original target and surrounding entries in Ghidra using
  `DumpPpcRange.java` in a read-only session.
- Added a precise function hint and rebuilt with the existing Windows preset.

## Evidence

- The user reports a black screen and crash when starting gameplay.
- The run begins at 12:16:22 on 2026-10-31 and terminates at 12:17:17.
- The last runtime message is:
  `Call to invalid or unregistered function at guest address 0x8471B2F0`.
- Windows records exception `C0000409` in `ucrtbase.dll`, consistent with the
  runtime fatal termination. This record alone does not identify a graphics fault.
- The old generated mappings include neighboring `8471B2E0` and `8471B2F8`,
  but omit `8471B2F0`.
- At `8471B2F0`, the original big-endian instruction word is `4BFFDB30`:
  an unconditional, non-linking branch to `84718E20`. The next word, at
  `8471B2F4`, is zero padding. The destination already has a registered function.

## Correction

Added `0x8471B2F0 = { size = 4 }` to `port/config/pointer_funcs.toml`.
This registers the original tail-call thunk and preserves its destination and
guest calling convention. It does not synthesize a return value or bypass the
destination function.

## Validation

- Windows code generation, compilation, and link: **PASS** with the pinned SDK.
- `PPCFuncMappings` now contains `8471B2F0`, and generated registration calls
  `SetFunction` for it. The generated body calls `sub_84718E20` and returns.
- Regression suite: **22 passed, 1 skipped** (the absent PS3 dump).
- Recognized inline tables: **1,762 compared**, zero truncations or disagreements.
- Generated `REX_FATAL` fallbacks: **0**.

### Second attempt and bounded family audit

After the first mapping fix, the user reports black followed by white before
gameplay, with audio briefly continuing. `ch2k8_005.log` starts at 12:25:25 and
terminates at 12:26:38 on a different unregistered address: **`8471B2E8`**.
Windows again records `C0000409` in `ucrtbase.dll`. The earlier `8471B2F0`
dispatch is no longer the final failure in this attempt.

Read-only Ghidra inspection covers the complete 25-slot family
`[8471B2B8, 8471B380)`, whose entries occupy eight-byte slots. Comparing every
entry with the generated registry identifies exactly three remaining gaps:

| Entry | Original body | Extent | Destination |
|---|---|---|---|
| `8471B2E8` | Mask `r3` to its low byte, then tail branch | 8 bytes | `84718DD0` |
| `8471B300` | Mask `r3` to its low byte, then tail branch | 8 bytes | `84718EA0` |
| `8471B308` | Tail branch, followed by zero padding | 4 bytes | `84718EC0` |

All destination functions already have registry entries. Added exact sizes for
all three. `8471B2E8` is runtime-observed; `8471B300` and `8471B308` are verified
sibling entries, not claimed to have caused an observed crash.

The generated-code execution test now compiles all four repaired gameplay
thunks into an ignored temporary harness with instrumented destinations.
It verifies the correct destination, low-byte masking only where present in
the original, propagation of the destination's return value, preservation of
`r4`, and preservation of LR. This does not execute the destination game logic
or constitute a gameplay test.

### Latest validation

- Native generation, compile, and link: **PASS**.
- All 25 entries in the inspected family are registered.
- Generated startup-loop and gameplay-thunk execution checks: **PASS**.
- Full regression suite: **23 passed, 1 skipped** (absent PS3 dump).
- Recognized inline-table audit: **1,762 compared**, zero truncations or disagreements.
- Generated `REX_FATAL` fallbacks: **0**.

A gameplay retry is required after the family fix. No successful court load or
gameplay result is claimed. The screen colors/audio report alone does not
establish a separate renderer defect.

## Confidence

- Missing runtime target and original branch instruction: **[CONFIRMED]**.
- The registration hint addresses the specific observed fatal dispatch:
  **[CONFIRMED]** structurally; successful gameplay remains unverified.
- The existing physical-memory protection warnings do not establish the cause
  of this fatal dispatch and are not changed by this correction.

## Open questions

- Does the rebuilt executable reach the court and allow play?
- Are additional callback targets or other paths reached only during gameplay?
- Can a complete exhibition game and Legacy save/load succeed?

Prior milestone: [user-confirmed menu boot](2026-10-31-menu-boot.md).
