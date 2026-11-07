# 2026-10-31: Gameplay flag callback

## Question and method

Why does the next longer gameplay attempt terminate? Inspect log 008 and the
original XEX through read-only Ghidra, then compile and exercise the recovered body.

## Evidence

- [CONFIRMED] `ch2k8_008.log` starts at 13:14:23 and ends at 13:15:51 with
  an invalid/unregistered call to `848E3A00`.
- [CONFIRMED] The complete five-instruction body at `[848E3A00,848E3A14)`
  loads a pointer from `[r3+0x10]`, loads its word at offset `0x1C`, clears
  the least significant bit, stores the word, and returns. Zero padding follows.
- [CONFIRMED] A raw pointer reference is present at `.data:84FDF788`.
  The bounded region `[84FDF700,84FDF900)` contains 42 distinct aligned
  code-pointer candidates; only this entry was missing from generated mappings.
  The data structure's full semantics are unknown; this is a bounded audit.

## Correction and validation

Register the original 20-byte body in `pointer_funcs.toml`. No flag operation
is bypassed. A generated-code execution test checks six flag values, including
high bits and all bits set, adjacent memory sentinels, and r3/r4/LR preservation.

- Native generation, compilation, and link: **PASS**.
- Generated-body execution check: **PASS**.
- Full regression suite: **26 passed, 1 skipped** (absent PS3 dump).
- Inline-switch audit: **1,762 compared**, zero truncations or disagreements.
- Generated `REX_FATAL` fallbacks: **0**.

## Conclusion and open questions

The observed failure is a missing indirect target. A runtime retry is required
after rebuilding. Gameplay stability and previously observed geometry corruption
remain unverified and unresolved respectively.
