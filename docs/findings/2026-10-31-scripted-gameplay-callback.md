# 2026-10-31: Scripted gameplay callback registration

## Question

Why does the attempt after the arena callback-table repair still terminate?

## Evidence and method

- `ch2k8_007.log` starts at 12:47:25 on 2026-10-31 and ends at 12:48:12 with
  `Call to invalid or unregistered function at guest address 0x84AB8CA8`.
- Windows records `C0000409` in `ucrtbase.dll`, consistent with runtime fatal
  termination rather than evidence of a GPU-driver exception.
- Read-only Ghidra inspection verifies a complete three-instruction body at
  `[84AB8CA8,84AB8CB4)`: materialize the global's high address, load `r3` from
  guest address `8586E310`, and tail-branch to `8497AA48`. Zero padding follows.
- The destination already has a generated registration entry.
- `FindGuestPointers.java` finds raw references in `.rdata`, including
  `8208E1C0`, `8208EA9C`, and `8208EBFC`. These occur among scripted-looking
  small-integer words and other code pointers. Their full format is not decoded.
- The bounded data region `[8208D000,8208F000)` contains **87 distinct
  code-pointer candidates**; this target is the only missing generated mapping.
  This is not a claim to have audited every scripted callback in the executable.

## Correction

Added `0x84AB8CA8 = { size = 12 }` to `pointer_funcs.toml`. The original global
load and tail call are preserved. No replacement return value or game logic
bypass is introduced.

## Validation

The optional generated-code test compiles this exact locally generated wrapper
with an instrumented destination and a reserved guest arena containing its
global word. It checks zero, ordinary, and high-bit-set 32-bit global values,
zero extension into `r3`, destination return propagation, and preservation of
LR and `r4`. It does not execute the destination game logic.

- Native generation, compilation, and link: **PASS**.
- The generated mapping now includes `84AB8CA8` and its body calls `8497AA48`.
- Generated global-load/tail-call execution check: **PASS**.
- Full regression suite: **25 passed, 1 skipped** (absent PS3 dump).
- Recognized inline-table audit: **1,762 compared**, zero truncations or disagreements.
- Generated `REX_FATAL` fallbacks: **0**.

A runtime gameplay retry remains required; no successful game start is claimed.

## Confidence and open questions

- Missing runtime target, original instruction body, pointer references, and
  existing destination mapping: **[CONFIRMED]**.
- Semantics of the surrounding scripted data are not established.
- Interactive gameplay, further missing callbacks, and the previously observed
  geometry corruption still require investigation.

Prior step: [arena introduction callbacks](2026-10-31-arena-intro-callbacks.md).
