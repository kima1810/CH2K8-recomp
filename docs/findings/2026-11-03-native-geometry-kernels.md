# Native geometry kernels: batching and shared address adaptation

## Scope and result

This work targets the three previously measured dominant guest geometry routines,
`84723778`, `84723CC0` and `84724930`, rather than another isolated helper.
Together they previously occupied approximately 55 seconds of one worker's
60-second gameplay window. The shaders, resolution, textures and lighting remain
at the existing full-quality configuration.

The final live interleaved comparison selects the previous native RAM kernel or
the new kernel randomly at each job boundary within one executable. During
seconds 120â€“180:

| Routine | Previous ns/work unit | New ns/work unit | Reduction |
|---|---:|---:|---:|
| `84723778` | 188.648 | 164.505 | 12.8% |
| `84723CC0` | 187.585 | 167.218 | 10.9% |
| `84724930` | 7,971.922 | 7,584.145 | 4.9% |

The two variants have closely matched work totals and wide-store totals. This
corresponds to approximately 10% less combined geometry-worker wall time at
equivalent work. These scopes include preemption and opt-in instrumentation.
The third work unit counts outer groups with variable inner work; its wide-store
totals provide an additional check on workload balance.

`tools/benchmark_geometry_jobs.py` alternates entire kernels on identical synthetic
descriptors and RAM, after checking their complete PPC contexts and 2 MiB memory
images match. The normal uncounted kernel gives:

| Routine | Previous median job | New median job | Median paired reduction |
|---|---:|---:|---:|
| `84723778` | 38.656 us | 33.511 us | 14.14% |
| `84723CC0` | 39.085 us | 32.031 us | 17.90% |
| `84724930` | 27.844 us | 25.956 us | 6.71% |

These are complete-job improvements, not scalar-vs-SIMD helper comparisons. The
synthetic third job differs in size from typical live jobs, so the absolute job
times should not be equated with live per-call values. Timings omit the first
pair and alternate execution order. They are not measurements on older hardware.

## Changes

1. Batch 29 independent normalization sites into groups of two, three or four.
   Their inputs are proven broadcast DPPS results. One packed square-root and
   division handles several distinct lengths, then restores each broadcast
   result. The same floating-point operations and rounding are retained.
   Nonfinite inputs use the original operations to preserve CPU-specific NaN
   payload behavior. Unmasked host FP exceptions select the original kernel.
2. Move the validated output-span decision outside the main loops. The native
   tail uses prepared stores directly. A failed checked stack reload jumps to
   the matching point in a copied byte-store tail, preserving the loaded value,
   all previous writes and the original remaining instruction order.
3. Reuse one prepared host-address bias for 56 proven palette reads and 48
   output stores. This removes repeated physical-alias adjustment without
   changing access width or order. The range proof includes those palette reads.
4. Reuse address adaptation in the two bounded 48-byte input streams. Exact
   stride, counter, backedge and address-copy shapes are checked. A span crossing
   the physical-alias boundary or wrapping the guest address space retains the
   fallback. Permissions and faults remain those of the original accesses.
5. Select the kernel once per function call. Counted and uncounted template
   instances retain diagnostic counts when requested and remove per-store
   counter increments during normal play.

The first normalization-only experiment, with conditionals inside the kernel,
did not improve live whole-function timings. Kernel separation and memory-address
adaptation supply the larger combined result. Alternative dot-product arithmetic,
a vectorized 10-bit unpacker, and a split output-store sequence were slower or
unhelpful and are not shipped. AVX2 and O3 trials did not justify a new CPU baseline
or compiler-policy change; the final build retains SSE4.1 and strict Release FP.

## Correctness and integration

The three complete corrected baseline bodies are pinned by SHA-256 before the
new transforms run. Unknown kernel edits require re-audit. The transforms still
derive the store/read bounds and scheduling dependencies; the body pins also
prevent changes elsewhere from invalidating those assumptions. Older generated
variants upgrade through the retained original bodies. Generated code stays
ignored and is produced by the codegen wrapper.

The CMake codegen command now depends on its Python transformation modules, so
updating a proof or transform regenerates cached sources automatically.

Validation includes 504 complete-routine context/RAM comparisons across original,
pack, unpack, store, native RAM, counted geometry and uncounted geometry paths,
plus 48 forced guarded-reload fallback comparisons. The arithmetic harness checks
800,000 input sets across rounding/flush modes, NaNs, infinities, subnormals,
signed zero, aliased operands, and FP status flags for all batch sizes. RAM tests
cover the physical alias, device exclusions, protected pages and write-watch
retry. Input-loop tests reject changed stride, counter, backedge and body shapes.

Project validation accounts for 166 passing tests and one environment-dependent
skip, including focused reruns after correcting the new loop-proof check. The
Release build and complete-job benchmark both pass. Diagnostic captures and
source-derived harnesses remain local in ignored output directories.

## Normal-play controls

Four visible 200-second runs use the same executable and unchanged runtime DLLs,
1280x720 native D3D12 targets, synchronous shader creation, and profiling disabled.
Only `ch2k8_geometry_batch` changes. Seconds 120–180 give:

| Run | Median interval | Submissions in 60 s | Mean submissions/s | p95 interval |
|---|---:|---:|---:|---:|
| Baseline A | 26.091 ms | 2,226 | 37.10 | 30.562 ms |
| Optimized A | 17.028 ms | 3,110 | 51.83 | 34.170 ms |
| Baseline B | 26.038 ms | 2,263 | 37.72 | 34.153 ms |
| Optimized B | 16.867 ms | 3,273 | 54.55 | 33.309 ms |

The optimized windows produce 39.7% and 44.6% more submissions than their
preceding controls. Median cadence is roughly 38 versus 59 Hz, but the full-window
means above better expose the slower frames. The p95 values do not establish
stable 60 FPS. Teams, cameras and arena complexity differ: the baseline readbacks use Arizona
State and Navy home courts, while the optimized readbacks use Hawaii and Coppin
State. Those venue differences can account for part of the throughput change.
This repeated observation does not prove an exact causal FPS multiplier. The within-run job comparison and identical-input
benchmarks provide the stronger attribution of CPU savings.

Native readbacks show coherent live Kentucky/Hawaii and Florida State/Coppin
State play, including the ball, players, court detail, crowd, lighting, shadows
and overlays. Process CPU use is approximately 1.9–2.1 cores in the baseline
windows and 2.8–2.9 in optimized windows while producing more frames; this is a
throughput improvement, not a claim of lower total process CPU use.

All four runs and the packaged executable share SHA-256
`467f93f1df56d987a327a174c18fa74fa43d64895e3d55d8cd2b653613fb57b0`.
The GPU/runtime DLL hashes are unchanged. An incremental build after the proof
updates regenerates no changed source and retains that executable hash.

## Controls and limits

`--ch2k8_geometry_batch=baseline` restores the previous native RAM kernels while
retaining preceding optimizations. `optimized` is the default; `compare` randomly
interleaves kernels and should be used with `--ch2k8_hot_log=PATH.csv`. The CSV's
`normalization_batch` column identifies the complete optimized kernel, including
its memory adaptations. The summarizer separates it from `native_ram`.

Full-game/Legacy/save completion, stable 60 FPS and older physical hardware remain
outside these bounded checks. Live demo scenes are not locked, and guest
submission cadence is not unique displayed FPS. The within-run work-normalized
comparison and identical-input job benchmark provide stronger attribution than
comparing unrelated demo scenes.

```powershell
python tools/benchmark_geometry_jobs.py
tools/benchmark_gpu_path.ps1 -Profile d3d12-rtv-extent -Visible -ShaderCompilation synchronous -HotFunctions -GeometryBatch compare
tools/benchmark_gpu_path.ps1 -Profile d3d12-rtv-extent -Visible -ShaderCompilation synchronous -GeometryBatch baseline
tools/benchmark_gpu_path.ps1 -Profile d3d12-rtv-extent -Visible -ShaderCompilation synchronous -GeometryBatch optimized
```
