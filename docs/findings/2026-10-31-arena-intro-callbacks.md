# 2026-10-31: Arena introduction callback-table gaps

Follow-up: the next attempt terminates at a different target in scripted data;
see [the scripted-callback finding](2026-10-31-scripted-gameplay-callback.md).

## Question

Why does the next gameplay attempt reach the arena introduction and then crash?

## Method

- Inspected user-provided screenshot evidence, `ch2k8_006.log`, and the matching
  Windows Application Error record.
- Inspected the original failing function and nearby code in read-only Ghidra.
- Used `FindGuestPointers.java` to locate its raw big-endian pointer references.
- Audited the containing interleaved record region against generated mappings.
- Added the two verified missing entries, rebuilt, and executed isolated
  generated-code callback tests with instrumented destinations.

## Evidence

The screenshot shows the Georgia Tech/Georgia matchup overlay, Stegeman
Coliseum, players, and crowd. Large black/stretched polygons are also visible.
This establishes partial arena-introduction rendering, not successful gameplay
or correct rendering.

The run starts at 12:35:33 on 2026-10-31 and terminates at 12:36:35 with
`Call to invalid or unregistered function at guest address 0x848B6FA0`.
Windows records `C0000409` in `ucrtbase.dll`, consistent with runtime fatal
termination. The geometry artifacts do not by themselves establish the cause
of that fatal call or identify a specific graphics defect.

### Original callback bodies

| Entry | Exclusive end | Original behavior |
|---|---|---|
| `848B6F98` | `848B6FA0` | Move `r6` to `r3`, then tail-call `84B85818` |
| `848B6FA0` | `848B6FBC` | Read `[r4+0x18]`, move `r6` to `r3`, test bit `0x4000`, then tail-call `84B85808` when set or `84B85C28` when clear |

`848B6FBC` is zero padding; a separate registered function begins at `848B6FC0`.
All three destinations already have registry entries. Only `848B6FA0` is
runtime-observed as a missing target in this attempt.

### Raw pointer references and bounded audit

`FindGuestPointers.java` locates `848B6FA0` at `.rdata:8206FC0C` and
`848B6F98` at `.rdata:8206FBEC`. Each is the second word of an eight-byte record.
The first word is small integer metadata whose meaning is not established here.

The containing contiguous region `[8206FA10,8206FFD8)` has **185 records** and
**86 distinct code targets**. The next words are floating-point-looking values
that do not match the record pattern; the prior words also break that pattern.
This is a structural region audit, not a recovered semantic definition of the
table or its metadata field.

Comparing all targets with `PPCFuncMappings` finds exactly two omissions:
`848B6F98` and `848B6FA0`. Both original bodies are independently inspected
before adding their exact extents to `pointer_funcs.toml`.

## Validation

- Native code generation, compilation, and link: **PASS**.
- Inspected record region after correction: **86/86 distinct targets registered**.
- Generated callback execution tests exercise clear/set flag paths, unrelated
  flag bits, correct target selection, `r6`-to-`r3` argument forwarding, return
  propagation, and LR preservation. Instrumented destinations isolate wrapper
  behavior; destination game logic is not executed by these tests.
- Full regression suite: **24 passed, 1 skipped** (absent PS3 dump).
- Recognized inline-table audit: **1,762 compared**, zero truncations or disagreements.
- Generated `REX_FATAL` fallbacks: **0**.

## Confidence and limits

- Runtime missing target, raw references, record words, instruction bodies, and
  generated mappings: **[CONFIRMED]**.
- The sibling's original entry is table-referenced and structurally verified;
  it is not claimed to have caused an observed crash.
- Gameplay after the fix needs a retry. No successful tip-off, interactive play,
  game completion, or resolution of the geometry corruption is claimed.
- The table metadata's semantics and the cause of the visible geometry
  corruption remain **unknown**. No renderer or allocation behavior was changed.

## Open questions

- Does the new build pass the arena introduction into interactive gameplay?
- What causes the stretched/black polygons?
- Are other indirect-call tables incomplete outside the audited regions?

Earlier gameplay-entry failures:
[callback-family investigation](2026-10-31-gameplay-startup-callback.md).
