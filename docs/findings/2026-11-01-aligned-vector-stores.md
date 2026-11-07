# Aligned vector byte stores — 2026-11-01

## Question

Can we reduce the remaining `stvlx` cost without widening guest-memory writes?
The [preceding profile](2026-11-01-remaining-hotspots-and-unpack.md) attributes
123/299 selected guest-thread executable samples to these byte-store loops.

## Method

Keep the generated effective-address calculation and `REX_STORE_U8` macro.
For a 16-byte-aligned address, replace the loop with sixteen explicitly ordered
byte writes, reading each source byte immediately before its write. Other
alignments retain the original loop. Do not prefetch/reverse the whole vector,
combine writes, cache allocation permissions, or bypass the physical-alias
adjustment. This avoids requiring a new RAM-versus-device-memory decision.

The repeatable codegen transform adds this fourth variant at **48 sites**:
16 each in `84723778`, `84723CC0`, and `84724930`. Existing original, pack-only,
and pack/unpack bodies remain available. Version-three migration recognizes
the two earlier transform versions and rejects unexpected store emission.

Use `ch2k8_vector_store=compare` to randomly interleave the preceding pack/unpack
body with the new body once per function call. The existing timing scope records
wall time and descriptor-derived work counts in separate CSV bins. These are
routine timings, not CPU cycle counts or complete frame times. Scheduling,
cache state, code layout, and variable inner work can affect them; the third
routine's outer-work normalization is less precise.

## Evidence

### Correctness and isolated timing

- **[CONFIRMED]** 28,672 instrumented byte-write traces match in address, value,
  count and order. Coverage includes all offsets across seven pages: ordinary
  RAM, graphics `7FC80000`, audio `7FEA0000`, the physical-alias threshold, and
  the top guest-address page. Device windows are logged, not actually written.
- **[CONFIRMED]** 32 overlapping source/destination comparisons preserve the
  original read-after-write behavior. A vector-wide temporary would not
  preserve this behavior for every overlap.
- **[CONFIRMED]** 4,096 ordinary memory offsets produce byte-identical complete
  buffers in the standalone native benchmark.
- **[CONFIRMED]** 252 complete generated-function comparisons match all PPC
  context bytes and two MiB of guest-memory writes against the retained body.
  This includes the preceding 12 random-data descriptors per routine with
  four-byte output alignments, plus 16 bounded finite-data descriptors covering
  all output alignments. All three optimized variants are checked.
- Expanding arbitrary random data to byte-misaligned outputs initially exposed
  a NaN sign difference in an existing pack-only copy's temporary vector
  register, with no guest-memory difference in that case. Compiler-generated
  arithmetic can choose different NaN signs in duplicated bodies. We retain
  the earlier random coverage and use finite data for the added alignment
  coverage; this is not proof of bit-identical results for every possible
  floating-point input to the complete routines. The individual integer
  pack/unpack boundary and random-bit tests remain unchanged.

Seven alternating timing trials (`-O2`, same host) give medians:

| Address alignment | Original ns/store | New ns/store |
|---|---:|---:|
| 0 | 9.9042 | 4.5333 |
| 4 | 7.7307 | 7.7310 |
| 8 | 5.8068 | 5.7883 |
| 12 | 3.6379 | 3.6640 |
| 1 | 9.3281 | 9.3382 |
| 15 | 1.7082 | 1.7084 |

The aligned isolated operation takes about **54% less time**. This is not a
whole-routine or whole-game speedup. Partial-store timings are roughly unchanged.

### Interleaved rendering run

Local run `20261101-085632-761-store-compare` uses D3D12/ROV at 1280×720,
60 Hz, optimized pack/unpack, and randomized store selection. Seconds 120–180:

| Function | Prior calls | New calls | Prior ns/work | New ns/work | Reduction |
|---|---:|---:|---:|---:|---:|
| `84723778` | 200,802 | 199,237 | 290.112 | 247.923 | 14.5% |
| `84723CC0` | 100,108 | 99,911 | 287.835 | 244.333 | 15.1% |
| `84724930` | 100,456 | 99,705 | 12,405.562 | 10,578.882 | 14.7% |

Seconds 60–120 independently show reductions of approximately 14.8%, 15.1%
and 14.5%. These reductions are additional relative to the previous combined
pack/unpack path; do not add them directly to earlier percentage improvements.

**[CONFIRMED]** Native output readback at about 180 seconds shows live play with
coherent court, players and HUD, a **4:31** clock and **0–0** score. The run is
deliberately stopped after about 210 seconds. No fatal entry occurs during the
bounded run. Median guest submission interval over seconds 120–180 is
**67.657 ms** (14.78 submissions/s). This mixed-path run is not a controlled
whole-game FPS comparison with earlier matchups.

## Conclusion and confidence

**[CONFIRMED within the tested cases]** Removing aligned-loop overhead reduces
measured routine cost while retaining byte-store semantics. The new path is
enabled by default within optimized pack/unpack. Use
`--ch2k8_vector_store=baseline` to restore the preceding implementation, or
`compare` with `--ch2k8_hot_log=PATH.csv` to repeat interleaved timing. Baseline
pack or unpack also bypasses the store path. Normal launches leave profiling off.

Both Windows Release builds pass. The repository suite has **54 passed,
1 skipped** (separate PS3 extraction absent). All **1,762** recognized inline
switch tables still match, with zero truncations/disagreements; generated fatal
fallback sites remain zero. Raw logs, captures, executables and generated game
code stay local and ignored.

## Open questions

Default-only run `20261101-090119-757-store-default` requests no pack/unpack/store
flags and leaves hot-function aggregation off. The runtime confirms the
optimized store default. Native readback at about 180 seconds shows live play,
coherent court/players/HUD, a **4:07** clock and **2–2** score. It remains running
until deliberately stopped after about 220 seconds, with no fatal log entry.
Seconds 120–180 give **57.132 ms** median guest submission interval
(17.50 submissions/s). Matchup/camera/state differ from prior tests; this does
not establish a controlled whole-game speedup. A short sampling interval below
also overlaps this window.

Fresh sampling of this default path takes 300 rounds across three CPU-heavy
threads, at a requested 20 ms interval. Of 900 observations, 300 are in the guest
executable: `84723778_store_fast` 122, `84724930_store_fast` 102,
`84723CC0_store_fast` 62, `84723450` 10, `847259D0` 3, and `84724268` 1.
Approximate source-operation attribution gives **112 store samples**, 44 pack,
35 unpack and 21 `lvlx`. Sources match the PDB checksums. Inline helpers and
compiler motion mean these are operation/call-site leads, not cycle accounting.
Equal sampling across selected threads is not whole-process CPU attribution.
The same three routines still account for 286/300 executable observations;
stores remain the largest lead despite the measured reduction.

Whole-match completion, Legacy/save stability, the reported black UGA head,
and overall lag remain open. Wider RAM stores still require evidence about
memory permissions, page boundaries, aliases and device-register behavior.
