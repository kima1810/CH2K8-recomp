# Packed-vector lane order after restoring Release optimization

## New profile

Profile the corrected optimized Release, adaptive presentation enabled, native
D3D12 targets with bounded ownership extents, 1280x720, visible window,
synchronous shader creation and opt-in hot-function logging. A 200-second run
records function totals during seconds 120–180:

| Guest function | Calls | Work units | Whole-function wall time |
|---|---:|---:|---:|
| `84723778` | 564,197 | 133,896,421 | 23.496 s |
| `84723CC0` | 282,099 | 65,072,490 | 11.671 s |
| `84724930` | 282,159 | 2,474,329 | 19.440 s |

The first two count descriptor groups; the third counts outer groups with
variable inner work. Together they occupy 54.606 seconds of a worker's 60-second
window. Logging includes scope overhead and preemption; this is not GPU time.

A bounded gameplay sample of 300 rounds across three selected threads contains
100 observations in `84723778_ram_fast`, 96 in `84724930_ram_fast`, and 47 in
`84723CC0_ram_fast`. Other busy-thread observations include `84DCA290` (150),
`84DDA4D0` (48) and TLS accessor `84E04948` (22). Inspection finds shared-progress
counter comparisons and repeated retry calls in the latter family. Earlier
startup sampling was dominated by those retries. They are not identified as
expensive lighting math, and no progress checks or synchronization are removed.

Across all attributed gameplay source operations, packed-vector packing accounts
for 57 observations, vector-left loads 33, vector-left stores 30, unpacking 26,
and reciprocal-square-root sequences 11. These counts guide investigation;
compiler line attribution is approximate and the three threads have different
roles. Matching PDB file checksums are checked before source attribution.

## Implemented change

`Ch2k8PackBiased64` now clamps directly in PPC register order `[w,z,y,x]` and
extracts the packed fields from that order. This removes the initial reversal.
`Ch2k8UnpackBiased64` gathers bytes directly into destination register order,
adjusts the shifted-lane mask and bias constants accordingly, and extracts the
same scratch temporary from its new lane. This removes the final reversal.

Both retain all destination, temporary and scratch bits. They introduce no new
ISA requirement, approximate arithmetic, texture/lighting changes, memory
access changes or modified guest instruction sequences. Existing scalar
fallbacks and code-generation dispatch remain intact. The helpers are used in
the three measured geometry functions above.

## Local helper measurements

`tools/benchmark_packed_lanes.py` reconstructs the shipped SIMD helpers from
commit `7d6ea05`, reuses the existing scalar correctness checks, and alternates
eight timing pairs. It compiles with the production Release numeric policy and
SSE4.1 baseline. Results, generated harnesses and executables remain in `out/`.

| Helper, repeat measurement | Previous median | Current median | Median paired reduction |
|---|---:|---:|---:|
| Pack | 1.817 ns | 1.687 ns | 7.16% |
| Unpack | 1.258 ns | 1.152 ns | 8.50% |

The initial exploratory measurement yielded approximately 9.1% and 8.4% reductions
respectively. These short helper loops are sensitive to scheduling and frequency;
the direction repeats, but the percentages are not whole-game gains.

The scalar comparisons cover 317,848 pack inputs and 1,003,456 unpack inputs,
including boundary/NaN values, randomized bit patterns, both pack halves,
source/destination aliasing, and scratch-register preservation. Packing also
checks all host rounding modes and flush settings. The focused build, numeric,
memory and transform suite passes 15 tests. Release builds successfully.

## Live validation and limits

A second 200-second visible run reaches coherent Tennessee/Creighton gameplay.
Native readbacks show players, the ball, court, crowd, shadows and HUD; the clock
progresses from 4:52 to 4:19. During seconds 120–180 the median guest submission
interval is 26.100 ms, with 2,098 submissions. The preceding profile run had
30.039 ms and 2,052 submissions. Scenes and camera behavior differ, so the median
change does not establish an FPS improvement.

Normalized whole-function costs are much closer:

| Function | Previous ns/work unit | Current ns/work unit |
|---|---:|---:|
| `84723778` | 175.476 | 174.334 |
| `84723CC0` | 179.353 | 178.512 |
| `84724930` | 7,856.639 | 7,822.533 |

Those approximately 0.4–0.7% differences are small, unmatched-scene observations,
not a controlled causal estimate. No stable 60 FPS or older-hardware claim is
supported by this increment.

Further candidates include scattered indexed geometry loads and normalization
in the same routines. Vector-left loads already use a native 128-bit load plus
byte shuffle, so replacing an assumed byte loop would not address their actual
implementation. Reciprocal-square-root translation currently uses square root
and division; substituting a hardware estimate would change numerical behavior
and requires a separate accuracy and guest-semantics investigation.

Reproduction:

```powershell
python tools/benchmark_packed_lanes.py
tools/benchmark_gpu_path.ps1 -Profile d3d12-rtv-extent -DurationSeconds 200 -ShaderCompilation synchronous -Visible -HotFunctions
python tools/summarize_hot_functions.py RUN/hot-functions.csv --start 120 --end 180
```
