# 2026-11-01: Remaining CPU hotspots and SIMD unpacking

## Question

After enabling the measured packed-vector optimization, which functions and
operations still account for the slow guest loop? Continue with observed CPU
costs and bit-equivalent changes rather than attributing lag to GPU capacity.

## Fresh sampling

Run `20261101-010643-739-remaining-hotspots` uses the existing pack-only optimized
ROV build. Read-only process/thread CPU deltas identify two near-core-saturating
threads and a third busy graphics/driver thread. The sampler captures 300 rounds
per selected thread, requesting 20 ms between rounds. Target executable/PID
and thread ownership are checked; the tool now rechecks ownership after opening
each thread to protect against thread-ID reuse. Sampling is capped at 30 seconds.

The three threads produce 900 IP observations. The guest worker contributes
299 executable samples and one library sample. Among its executable samples:

| Function | Samples |
|---|---:|
| `84723778_fast` | 135 |
| `84724930_fast` | 107 |
| `84723CC0_fast` | 53 |
| `847259D0` | 2 |
| `84723450` | 1 |
| Other/unattributed | 1 |

The three known hot routines still account for **295/299** guest executable
observations. The other selected threads sample vertical-blank/kernel and
graphics-driver paths; these equally sampled threads must not be combined
into a purported whole-process CPU percentage.

The matching executable/PDB and source checksums associate guest observations
with generated source operations:

| Source operation | Samples / 299 | Approximate share |
|---|---:|---:|
| `stvlx` byte-store loops | 123 | 41.1% |
| `vupkd3d128` unpack operations | 49 | 16.4% |
| `vpkd3d128` pack operations | 23 | 7.7% |
| `lvlx` loads | 21 | 7.0% |

**[CONFIRMED]** This is source-line attribution from sampled native PCs, not
retired-instruction counts or exact cycle attribution. Compiler movement and
inlining can associate a PC with a nearby operation. The ranking is a useful
lead, not an instruction-level timing guarantee.

`tools/summarize_instruction_samples.py` uses `llvm-symbolizer` and
`llvm-pdbutil`. It requires the generated source MD5 to match the checksum
embedded in the PDB before attributing operations, and records executable/source
SHA-256 values. This avoids silently using line numbers from a changed codegen
file. Matching archived sources can be supplied with `--source-root`.
For this sample the retained original bodies and prior transform reconstruct
the previous local source version; all inspected source files match the PDB's
MD5 values. The pack-only executable SHA-256 is
`9fb518b5dd9c7d471cb3086435d3e049feb1197265981cc780f757ce4c83df7f`.

The host reports an Intel Core i7-10700F with eight cores and 16 logical
processors. That does not turn the serial guest worker into parallel work;
nominal CPU model frequency is not treated as a live-clock measurement.

## SIMD unpack candidate

The corrected type-6 unpack extracts three signed 20-bit fields and a high
four-bit field, reconstructing biased float bit patterns and replacing the
negative overflow encoding with a canonical NaN.

The new SSE4.1 helper selects bytes, shifts the two nibble-offset lanes, sign
extends in parallel, adds integer biases and selects canonical overflow NaNs.
It preserves native lane order, source/destination aliasing, and exact temporary
and scratch contents. It performs no floating-point arithmetic or FP mode
changes. No new CPU instruction-set requirement is introduced.

There are **58** eligible sites in the three hot routines: 16, 16 and 26.
Only those sites are replaced in the new variant. The original scalar and
pack-only variants remain available. A versioned codegen transformation restores
the retained baseline before upgrading its own generated copies; unfamiliar
dispatchers or emission shapes fail. Reapplying it is byte-idempotent.

## Correctness and measurements

- **[CONFIRMED]** 1,003,456 packed inputs, with distinct/in-place destinations:
  **2,006,912 unpack comparisons**. Boundary Cartesian products cover signed
  extrema, negative overflow and all 16 W values; a million further inputs
  cover random packed bits and poisoned unused halves. Destination, source,
  temporary and scratch state match the scalar conversion.
- **[CONFIRMED]** 72 complete generated-function comparisons now exercise both
  pack-only and pack-plus-unpack against the retained original bodies. All PPC
  context bytes and two MiB of guest-memory writes match, with original
  save/restore helpers and varied descriptor counts/output alignments.
- The standalone benchmark gives median costs of about **1.96 ns scalar** and
  **1.25 ns SIMD**: approximately **36% less unpack-kernel time** on this host.
  This is not a whole-frame speedup measurement.

ROV run `20261101-012121-766-unpack-compare` randomly interleaves pack-only and
pack-plus-unpack calls in the same process. Seconds 60–120 give:

| Function | Pack-only calls | New calls | Pack-only ns/work unit | New ns/work unit | Additional reduction |
|---|---:|---:|---:|---:|---:|
| `84723778` | 190,195 | 190,436 | 287.52 | 278.87 | 3.0% |
| `84723CC0` | 95,131 | 95,185 | 290.80 | 272.34 | 6.3% |
| `84724930` | 94,814 | 95,630 | 12,906.61 | 11,692.38 | 9.4% |

These are additional reductions relative to the previous pack-only optimization,
not percentages to add directly to earlier results. Descriptor normalization,
randomized interleaving and timing limitations are the same as in the
[earlier finding](2026-11-01-hot-functions-and-vector-pack.md); the third routine
has variable inner work and less precise normalization.

Native readback at about 170 seconds shows coherent live UMBC play with a visible
HUD, 4:40 clock and 3–0 score. The mixed run's median guest submission interval
is 71.528 ms over seconds 60–120. This is not a matched whole-game FPS comparison.

## Defaults, validation and next target

`ch2k8_vector_unpack=optimized` is now the default within optimized packing.
Use `baseline` for the preceding pack-only path, or `compare` to interleave both.
`ch2k8_vector_pack=baseline` still restores the fully retained original bodies.
The CSV adds `unpack_optimized`; the summary tool reads both old and new schemas
and separates `optimized` (pack-only) from `pack_unpack`.

Full regression suite: **51 passed, 1 skipped** (separate PS3 extraction absent).
Optimized-only runtime and final build results are recorded below.

The default-enabled optimized-only run
`20261101-012858-772-unpack-optimized` remains alive until deliberately stopped
after about 210 seconds. Its native readback at approximately 180 seconds shows
coherent live play, visible court/players/HUD, a **4:49 clock and 3–0 score**.
No fatal entry occurs during that bounded test. During seconds 120–180, median
guest submission interval is **68.628 ms** (14.57 submissions/s). Matchup,
camera and scene state differ from earlier captures, so this does not establish
a controlled whole-game FPS gain.

Both Windows Release builds pass. The established control-flow audit still
compares all **1,762** recognized inline tables with zero truncations or
disagreements; generated fatal fallback sites remain zero. New tests also cover
old-transform migration, byte-idempotence, old/new timing schemas and rejection
of stale source/PDB combinations.

The largest remaining measured lead is the byte-by-byte `stvlx` path. The pinned
runtime's graphics and audio register windows are at `7FC80000` and `7FEA0000`,
inside a range excluded from normal heap lookup. Any future widening should
first establish a writable RAM region, bound the complete byte extent and
preserve alignment, partial-store, page and physical-alias semantics. No guest
store width or memory behavior is changed by the unpack optimization.

Raw profiles, generated code, source snapshots and framebuffer images remain
local and ignored. Full-game completion, Legacy/save stability, the reported
black UGA head and remaining lag are still open.
