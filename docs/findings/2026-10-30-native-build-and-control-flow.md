# 2026-10-30: Native build and control-flow recovery

Follow-up: [2026-10-31 menu boot](2026-10-31-menu-boot.md) records the user's
successful menu boot. Gameplay remains untested. The automated observations
below retain their original, narrower scope.

## Question

Can the existing Windows recompilation skeleton build from the USA retail XEX,
and can the 16 recorded generated fatal fallbacks be resolved from executable
evidence rather than suppressed?

## Method

- Extracted the user-provided full-disc ISO with `tools/xdvdfs.py` into the
  manifest's existing `work/ch2k8/XBOX/disc` layout. Source media was unchanged.
- Verified the archive with `ch2k8_archive.py verify` and ran the archive tests.
- Reproduced code generation using the pinned ReXGlue
  `0.10.0.24-dev.gbd833a2` Windows SDK. Its release ZIP SHA-256 is
  `1e19d7ec9be0d9d7e1a0088a34a33b068d4dea520181e81318528ef3b37627e7`.
- Imported the retail XEX into Ghidra 12.2 / Java 25.0.5 using Xenon360 0.8.2.
  Used `ghidra/DumpPpcRange.java` to inspect instructions and raw big-endian
  words around the affected sites. Auto Analysis was disabled for these bounded
  inspections; this is not a completed whole-program analysis.
- Added explicit exclusive function ends and nine individually inspected switch tables to
  `port/config/control_flow.toml`, then regenerated and built with the existing
  Windows CMake preset.
- Investigated invalid-shift compiler diagnostics and added a narrow automatic
  correction for the pinned SDK's `vupkd3d128` sign extension, with numeric tests.

## Evidence

### Input and archive

- `default.xex`: 38,424,576 bytes; SHA-256
  `71e8983d1cc009e485696aad19b5fa4b4661761870e2c8972717b932c1e4be36`.
- Disc archive: `0A` through `0M`, 13 parts, 3,378 entries, alignment `0x800`.
- Header/part/TOC round-trip: **IDENTICAL**, 54,280 bytes; zero duplicate hashes,
  zero size anomalies, ascending hash order.
- Archive tests with a workspace-local pytest temporary directory:
  **8 passed, 1 skipped** (PS3 dump absent). An initial sandbox test invocation
  could not create pytest's external temporary directory; `--basetemp` inside
  the workspace resolves that environment issue without changing the tests.

### Baseline versus corrected generation

The baseline completes successfully but emits **16 `REX_FATAL` sites**. The
older findings group them into three functions; direct inspection finds them
in **five generated functions**: `84C208D8`, `84C20A50`, `84C20AE8`,
`84D40778`, and `84DAB6FC`. Two of the sites in the first function are jump
targets; the other 14 are conditional branches.

Several supposedly unresolved targets already have `loc_...` labels in the
same generated C++ function. This is evidence that the emitted body and inferred
function bounds disagree, rather than evidence that those branches are invalid.

The corrected run completes successfully and emits **zero `REX_FATAL` sites**,
with **53,795 function declarations**. No generated C++ is hand-edited or committed;
the separate automatic SDK expression correction is described below.
The very large `84E75D28` initializer still produces a size warning; its C++
body is 8,815,912 bytes. `84B6ACB8` also exceeds the 1 MiB partition target.

### Explicit function bounds

| Start | Exclusive end | Evidence |
|---|---|---|
| `84B8A368` | `84B8A608` | Startup dispatch and five case bodies join at `84B8A574`; tail-return at `84B8A604`; separate trampoline starts at `84B8A608` |
| `84C208D8` | `84C20A4C` | Two inline dispatches, shared branch blocks, final `blr` at `84C20A48`; padding precedes the next entry |
| `84C20A50` | `84C20AE8` | Separate entry, inline dispatch, branch to the late block at `84C20AD8`, final `blr` at `84C20AE4` |
| `84C20AE8` | `84C20B90` | Separate entry, inline dispatch, late block at `84C20B78`, final `blr` at `84C20B8C` |
| `84D40778` | `84D40850` | Six inline pointers and multiple return blocks; last `blr` at `84D4084C`, next function begins at `84D40850` |
| `84DAB6E8` | `84DAB720` | Initial object load/null check precedes the old inferred `84DAB6FC` entry; both null paths share `84DAB6F4` |

At `84DAB6E8`, the code loads `r11` from `0x21C(r3)`, checks it for null,
and branches to `84DAB6FC` only for a non-null value. The block at `84DAB70C`
branches back to `84DAB6F4`, which sets the return value to zero. Declaring the
whole function incorporates both paths and removes the spurious interior
function entry from the generated mapping.

### Recovered inline tables

Each dispatch uses `rlwinm` to scale the original selector into `r0`, loads an
absolute big-endian pointer, transfers it to CTR, and executes `bctr`. Thus the
manual switch register is the **unscaled selector**, not `r0` or CTR. Every
listed pointer was read from the imported executable. The arrays end where
case instructions begin; all destinations stay inside the declared owner.

| `bctr` | Table start | Selector | Targets in original index order |
|---|---|---|---|
| `84C20904` | `84C20908` | `r10` | `84C20A48`, `84C20A48`, `84C20918`, `84C2092C` |
| `84C20964` | `84C20968` | `r10` | `84C20978`, `84C209AC`, `84C209E0`, `84C20A48` |
| `84C20A7C` | `84C20A80` | `r10` | `84C20AE4`, `84C20A90`, `84C20AE4`, `84C20AA4` |
| `84C20B14` | `84C20B18` | `r10` | `84C20B28`, `84C20B8C`, `84C20B3C`, `84C20B8C` |
| `84D407B4` | `84D407B8` | `r3` | `84D40838`, `84D407D0`, `84D407E8`, `84D407F4`, `84D407DC`, `84D40800` |
| `84B8A40C` | `84B8A410` | `r11` | `84B8A46C`, `84B8A424`, `84B8A4AC`, `84B8A4F4`, `84B8A53C` |
| `84D3688C` | `84D36890` | `r7` | `84D368B8`, `84D368B8`, `84D368C0`, `84D368C8`, `84D368B8`, `84D368B8`, `84D368C0`, `84D368C8`, `84D368D0`, `84D368D0` |
| `84D3AD78` | `84D3AD7C` | `r27` | `84D3ADA4`, `84D3ADA4`, `84D3ADAC`, `84D3ADB4`, `84D3ADA4`, `84D3ADA4`, `84D3ADAC`, `84D3ADB4`, `84D3ADBC`, `84D3ADBC` |
| `84D422BC` | `84D422C0` | `r11` | `84D422E8`, `84D422E0`, `84D422D8`, `84D422D0` |

For example, the baseline emits only two cases for `84C20904` and one case
for `84D407B4`. Recovering full tables restores valid cases that previously
would hit the generated default trap even though they were not counted among
the 16 `REX_FATAL` sites. Default out-of-range traps are retained.

### Build and startup

Toolchain: Clang 23.1.4, CMake 4.4.4, Ninja 1.13.2, Microsoft C++ tools
14.39.33519, Windows SDK 10.0.26100.0. Configuration succeeds with the existing
`win-amd64` preset. The first native compilation and link succeed, including
the large initializer, producing `ch2k8.exe` and staging the runtime/Xenos DLLs.

That initial build exposes another correctness blocker: generated
`vupkd3d128` packed signed 20-bit extraction casts a 64-bit value to `int32_t`
**before shifting right by 44**, which is undefined behavior. The intended
sign extension needs a signed 64-bit intermediate, followed by the existing
assignment to the 32-bit destination. The SDK source's vector builder also
contains this expression, so this is a generator issue rather than a game
function-boundary problem.

`tools/fix_codegen.py` corrects only the three exact emitted forms (left shifts
44, 24, and 4, followed by right shift 44). CMake orders the correction after
codegen and before compilation. Both Python scripts are dependencies of the
codegen command, which completes correction before Ninja checks its source
outputs. It corrects **489 expressions in
8 files**. Clang's `-Werror=shift-count-overflow` prevents accepting another
oversized shift silently. This is a local compatibility workaround for the
pinned SDK, not a claim that the upstream SDK was fixed.

Tests compile the corrected expressions with the oversized-shift diagnostic
enabled as an error, then compare all three extracted lanes against known
values: zero, positive, negative, signed 20-bit minimum/maximum, and all minus
ones. The packed fourth component is nonzero to check isolation. Idempotence
and preservation of unrelated shifts are also tested. Combined suite:
**22 passed, 1 skipped** (PS3 dump absent), including the audit, timestamp, and generated
startup-loop tests below.

The corrected native build also links successfully with **zero compiler
warnings/errors**. An unchanged-build check then exposes the pinned SDK's
manifest timestamp behavior: it rewrites the identical `sdk_version` line
after writing the generation stamp. Ninja keeps treating codegen as dirty,
which in turn invalidates the correction stamp and compiled objects.

Touching the completion stamp alone did not resolve the observed Ninja
dependency behavior. `tools/run_codegen.py` instead records manifest bytes and
timestamps before invoking the SDK and restores the timestamp only after a
successful invocation whose resulting bytes are identical. Actual content
changes and failures are preserved. CMake includes a build-directory copy of
the SDK boilerplate with just that command wrapped, and checks the expected
command shape explicitly rather than silently accepting an incompatible SDK.
The original generated boilerplate is untouched. The same wrapper applies the
VMX correction before returning to Ninja. It preserves generated C++ timestamps
only when the final corrected bytes match their previous SHA-256, so rewriting
broken SDK output and immediately correcting it does not cause unnecessary
recompilation. Actual changed bodies keep their new timestamps. Unit tests cover
a successful no-op rewrite, a genuine version change, a failed invocation,
unchanged corrected C++ output, and changed corrected C++ output.

An unchanged native build now exits successfully with **`ninja: no work to do.`**
When the callback hint below changes, regeneration writes 13 files, but the
wrapper preserves unchanged corrected outputs: only three translation units
need recompilation before linking. Windows linking now preserves generated line
tables in a PDB to make subsequent native crash localization practical.

### Startup blockers discovered after linking

1. First startup initializes the Xenos GPU/runtime, registers 53,795 functions,
   and loads the XEX, then terminates on an unregistered indirect target
   **`84DF1840`**. Ghidra verifies a complete one-instruction body, `blr`, at
   that address, immediately after the CTR trampoline at `84DF1834`. Added a
   four-byte function entry to `pointer_funcs.toml`; this preserves the real
   no-op return rather than fabricating a game hook. Regeneration registers
   53,796 functions and startup passes this failure.
2. The next run reaches audio initialization/callbacks, then exits with Windows
   exception **`C000001D`** (illegal instruction). The application event records
   native RVA **`017A2C90`**; disassembly confirms `ud2`. The executable's
   `PPCFuncMapping` guest/host pairs locate that PC inside **`84B8A368`**, whose
   generated body contains a switch with only case 0 and a default trap.
   Ghidra verifies five inline pointers at `84B8A410` through `84B8A420`, followed
   immediately by the first case at `84B8A424`. Added all five targets, selector
   `r11`, and the owning function's end at `84B8A608`.

3. After the five-case switch is restored, the PDB resolves the next illegal
   instruction to **`84D36860`**. Its loop initializes `r7=0`, skips exactly
   indices 3 and 7, and continues through index 9. The generated first dispatch
   has only cases 0 through 7. The inline table at `84D36890` has **ten** words;
   indices 8 and 9 both point to `84D368D0` (`li r10,4`). Added the complete
   table at `bctr 84D3688C`, using unscaled selector `r7`.
4. Startup then passes that site and reaches the same error in **`84D3AC68`**.
   Its `r27` loop likewise reaches 8 and 9 despite equality checks that skip
   3 and 7. The ten words at `84D3AD7C` end immediately before the first case;
   the two missing targets both lead to `84D3ADBC` (`li r31,4`). Added the full
   table for `bctr 84D3AD78`, selector `r27`.

An optional integration test extracts only the locally generated `84D36860`
function into an ignored temporary C++ harness, compiles it against the SDK,
reserves a guest address arena with one readable table page, and executes the
actual loop. An independent layout calculation predicts **10,864 bytes**;
the generated function returns that value without taking a default trap.
No generated game code is checked into the test or repository. The test skips
when Windows, the local SDK, generated sources, or Clang are unavailable.

5. After both layout loops are corrected, startup reaches GPU interrupt setup
   and controller discovery, then reports an unregistered indirect target
   **`84E20368`**. The original body performs an index check, returns an error
   for an invalid index, and otherwise tail-calls through a virtual method.
   Added its verified extent `[84E20368, 84E203B0)` to `pointer_funcs.toml`.
6. Startup then reaches **`84D42250`**, whose word-copy dispatch at
   **`84D422BC`** is emitted with only case 0. The original has four consecutive
   pointers, followed by case bodies that intentionally fall through to copy
   one through four words. Added all four targets in their original order.

The startup logs also report `MmAllocatePhysicalMemoryEx: bad protection bits`
and an `IoDismountVolumeByFileHandle` stub. These messages alone do not establish
that either caused the observed fatal sites; the identified missing callbacks
and default traps were addressed without changing allocation semantics.

7. After the word-copy fix, the PDB resolves another default trap to
   **`847E35C8`**. Its dispatch at `847E3728` contains only one generated case.
   This motivates the systematic audit below, which recovers its complete
   twelve-entry table along with other truncated prefixes.

### Systematic inline-table audit

`ghidra/ExportInlineSwitches.java` walks `.text` without modifying the program.
It accepts only the exact six-instruction `lis r12` / `addi r12` /
`rlwinm r0,selector,2,0,29` / `lwzx r0,r12,r0` / `mtctr r0` / `bctr` pattern.
The computed table base must be the word immediately following `bctr`.
It reads at most 4,096 entries, requires every target to be aligned and inside
`.text`, requires the array to end exactly at its earliest case body, and
requires every target to decode. Backward, non-inline, relative, differently
shaped, or structurally ambiguous tables are excluded.

The exporter finds **1,762** validated tables. `tools/audit_inline_switches.py`
matches all 1,762 against generated dispatches, using the actual C++ switch
selector. It proposes a hint only when every existing target matches the
original table's prefix and the original contains more cases. Equal-length
target disagreements or selector differences are reported instead of repaired.

After the nine individually inspected fixes, this identifies **28 additional
truncated tables**, omitting **257 cases**, with **zero target/selector
disagreements**. The largest recovered table has 80 entries. Their exact
targets, owning generated functions, and old/new case counts are recorded in
`port/config/inline_switches.toml`. Together the two hint files specify **37
tables**. Regeneration and the native rebuild both succeed, with no generated
fatal fallbacks and no compiler warnings. The follow-up audit compares all
1,762 tables with **zero remaining truncations and zero disagreements**.
Other switch idioms and arbitrary indirect calls remain outside this audit.

### Final local validation

- Native Windows Release build and link: **PASS**, with PDB and staged runtime/
  Xenos DLLs. Final registration surface: **53,796 functions**.
- Unchanged rebuild: **`ninja: no work to do.`**
- Generated `REX_FATAL` sites: **0**, down from the reproduced baseline's 16.
- Validated inline-table comparison: **1,762 / 1,762 matched**, zero truncations
  or disagreements after hints.
- Tests: **22 passed, 1 skipped**; the only skip is the unavailable PS3 dump.
- Final bounded startup: **remained alive for 30 seconds**, then intentionally
  stopped by the test. The log records GPU/runtime/input/audio initialization,
  shader translation/pipeline creation, GPU interrupt setup, and controller
  discovery. No fatal call or illegal-instruction exit occurs in that window.

This automated test alone is **not a confirmed menu or gameplay result**. The application was run
with `--headless` for log-based observation; no visual legal-screen/menu check,
input-to-menu test, exhibition game, or Dynasty/save test was performed.
Physical-memory protection errors and kernel/network stubs remain in the log.
Surviving the observation window does not prove forward progress or rule out a
hang. These are explicit follow-up runtime investigations, not suppressed
errors or claimed successes.

## Conclusion

The known fallback sites can be resolved through declarative analysis fixes,
without fatal suppression or fabricated return values. Full switch arrays also
recover cases that the baseline silently omitted. The separate SDK VMX
expression correction is applied reproducibly by the build wrapper.

## Confidence

- Input identity, archive verification, table words, branch destinations,
  corrected code-generation result: **[CONFIRMED]** by local inspection/run.
- The selected function ownership is supported by entry instructions, local
  branches, dispatch targets, and terminal instructions. This is structural
  evidence; gameplay equivalence has not been established.
- The prior eight function-start hints in `pointer_funcs.toml` remain
  **[GUESS]**; this investigation does not independently validate all eight.
  The additional `84DF1840` and `84E20368` entries are **[CONFIRMED]** by runtime
  calls and their complete original instruction bodies.
- Zero generated fatal fallbacks does not establish complete indirect-call
  coverage or a playable port. Runtime kernel/GPU/audio behavior remains to be
  tested separately.

## Open questions

- Menu boot is now user-confirmed in the [2026-10-31 follow-up](2026-10-31-menu-boot.md).
  Legal-screen presentation was not separately reported.
- Are non-inline/relative switches or other idioms outside the audited exact
  pattern also truncated without explicit fatal diagnostics?
- What causes the physical-memory protection warnings, and are the kernel/
  network stubs or guest state blocking forward progress after initialization?
- Do all dynamic call targets have correct entries, and do SDK runtime imports
  cover the paths needed for exhibition games and Dynasty?

All local game files, generated sources, Ghidra databases, SDKs, and raw logs
remain ignored. The contribution contains only configuration, scripts, and
research/build documentation.
