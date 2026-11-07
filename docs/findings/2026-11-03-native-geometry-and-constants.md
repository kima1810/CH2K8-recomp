# Geometry and shader-constant overhead

## Scope and function attribution

The renderer already executes translated vertex/pixel programs as native GPU
shaders. Lighting and geometry are not a single Xbox service that can be switched
off. This change removes draw-invariant compatibility work around those programs;
it preserves their transform, skinning, lighting and floating-point calculations.
The anonymous guest CPU routines are not assigned lighting names without evidence.

Reviewed functions in the pinned SDK:

| Function | Work removed |
|---|---|
| `PipelineCache::GetCurrentVertexShaderModification` | Determines a common byte order from the analyzed shader's used vertex-fetch constants and includes it in the shader key. |
| `D3D12CommandProcessor::IssueDraw` | Keys the exact index byte order and read-only shared-memory binding using the same decisions passed to binding and constant upload. |
| `DxbcShaderTranslator::ProcessVertexFetchInstruction` | Emits only the necessary byte swaps and one read-only fetch path for eligible draws. |
| `DxbcShaderTranslator::StartVertexShader_LoadVertexIndex` | Emits only the known index swap; preserves the original GPR0.y initialization even when no swap is needed. |
| `Ch2k8ChangedConstantVectors` | Compares complete shader float4 values using integer SIMD, retaining scalar partial-vector checks. |
| `Ch2k8ChangedConstantsUsed` | Intersects changed/used bitsets by 64-bit blocks rather than testing each vector. |

The constant bookkeeping applies to both D3D12 and Vulkan and to all float
constants, including parameters consumed by transform and lighting programs.
Integer comparisons preserve NaN payloads, signed zero and every other bit.

## Compatibility and controls

`ch2k8_native_vertex_fetch` is enabled by default on D3D12. It applies to both
native render targets and ROV. `--no-ch2k8_native_vertex_fetch` restores the
original dynamic geometry shaders. Mixed stream byte orders retain dynamic
attribute swapping while known index/binding state can still be specialized.
Draws using vertex or pixel memory export retain the entire original geometry
path, including UAV access. No synchronization, memory watching, depth checks,
texture validation or occlusion behavior is disabled.

The shader modification layout has a new cache version. All geometry decisions
are part of the shader/PSO key, so changed fetch registers or index formats select
the correct variant. The draw path also compares the specialized state against
the original system constants before binding. The tests exercise 4,915,200 key
combinations and the actual generated draw-key code, including memory-export
and disabled fallbacks.

`--no-ch2k8_native_constants` retains the existing baseline constant-update path.
Changed-vector tests cover aligned and partial vectors, pre-existing changed
bits, bank boundaries, every usage span in a 256-vector bank, and packet tails
ending at inaccessible memory pages.

## CPU bookkeeping measurement

`tools/benchmark_render_constants.cpp` compares the original scalar loops with
the production helpers using warmed, alternating local trials. Median
nanoseconds per call on this machine:

| Operation | Original | New |
|---|---:|---:|
| Changed masks, 16 words | 7.720 | 5.463 |
| Changed masks, 64 words | 25.497 | 14.643 |
| Changed masks, 256 words | 101.257 | 51.555 |
| Changed masks, 1024 words | 383.832 | 203.257 |
| No-intersection usage scan, 256 vectors | 156.561 | 5.116 |

These are approximately 29–49% lower changed-mask costs and 97% lower cost for
the full no-intersection scan. The packet pattern matters: this is a local
microbenchmark, not a whole-game performance ratio.

## Shader and output validation

Two bounded ROV runs generated dynamic/specialized pairs in the same executable
using diagnostic `--ch2k8_vertex_fetch_compare`. The final geometry recording
contains 83 paired variants from 81 distinct guest vertex programs:

| Static generated-code metric | Dynamic | Specialized |
|---|---:|---:|
| Instruction slots | 36,870 | 29,794 |
| Switch sites | 1,003 | 83 |
| Conditional branch sites | 626 | 249 |

This is about 19% fewer static instruction slots and 92% fewer switches across
those pairs. It is not a count of executed instructions or a GPU timing ratio.
The final key states in the recording use read-only binding; memory-export
specialization is deliberately not enabled.

The dynamic bytecode for guest vertex shader `969B0EFC70458B80` matches the
previous reference capture's shader byte for byte. Its specialized variant
reduces 518 instruction slots to 474, and seven switches to one. The offline
RenderDoc tool now supports vertex shader replacement. Replacing that shader
in the same reference workload yields byte-identical, nonzero full 10 MiB
EDRAM at events 58,287, 48,863 and 174,576.

After warming both variants, three alternating paired GPU counter trials yield
median summed-action reduction of only 0.0005%, and target-draw reduction of
0.07%. These are effectively unchanged timings in this pixel-heavy workload.
The earlier byte-order-only experiment was likewise effectively unchanged.
Static compatibility work is removed, but neither experiment establishes a
displayed-FPS improvement. No lighting quality was reduced to obtain the result.

The ROV live capture renders the court, players, crowd, shadows and overlays
without a specialized-state mismatch. All captures, bytecode and detailed local
logs remain ignored. Full-game completion and all lighting/material variants
remain outside this bounded validation.

## Final checks

The final full suite passes **149 tests with one environment-dependent skip**.
The patched dual-backend SDK, native replay tools and Release game build
successfully. A 15-second startup check of the final staged runtime confirms
`ch2k8_native_vertex_fetch=true`, comparison mode off, and no state mismatch.
The build includes the retained-output lifetime fix described below. Source
changes and this report remain available for review in the working tree.

## Remaining overhead

**Follow-up:** [Native presentation and Release-build investigation](2026-11-03-native-presentation-and-release-build.md)
identifies false DXGI VBlank ticks and missing compiler optimization in the
current Release game. Its fixes supersede the unresolved pacing diagnosis below;
the original observations are retained as historical evidence.

The final native-render-target live check exposed a separate slow-pacing
condition. Three 200-second runs at 1280x720, with bounded extents and synchronous
pipeline creation, show these median guest submission intervals over seconds
120–180:

| Geometry path | Median interval |
|---|---:|
| Specialized | 694.340 ms |
| Original dynamic geometry | 700.492 ms |
| Specialized, outside the sandbox | 689.699 ms |

These are unmatched autonomous scenes, so the small differences are not a speedup
measurement. The slow condition persists with specialization disabled and
outside the diagnostic sandbox. It is much slower than the historical
user-validated native-path run, and this work does not resolve that discrepancy.
Output remains coherent, with no geometry/pixel state mismatch logged.

A bounded sample of 200 instruction pointers per selected thread finds the
graphics thread waiting in `ZwWaitForSingleObject` for 194 of 200 samples.
Another thread is in `NtGdiDdDDIWaitForVerticalBlankEvent` for all 200, while the
UI thread includes driver, presentation and synchronization calls. This does
not establish that lighting/geometry math is the current bottleneck. Presentation
and driver scheduling need separate controlled profiling; the current changes
must not be described as a fix for the observed live slowdown.

That review also found a concrete native presentation lifetime bug. The VBlank
thread took a strong local output reference, unlocked its mutex, then called
the mutable shared member rather than that retained reference. It now calls
the retained output, so replacing or clearing the shared output cannot invalidate
the in-progress wait. A compiled test executes the actual patched block while
clearing the shared output at unlock and verifies its lifetime through the call.
This correctness fix does not change pacing or claim to resolve the slow condition.

Guest vertex-format decoding, texture address/tiling adaptation, command-buffer
processing, guest CPU work and ROV pixel/depth/blend emulation still exist.
Native vertex buffers would require validated layout/identity tracking and
coherence for rewritten buffers, including memory-export writes. Further
lighting specialization needs identified shader inputs and bounded variants.
Removing those mechanisms without equivalent replacements would alter the game.

Use `tools/capture_gpu_workload.ps1 -ShaderState optimized -VertexFetch compare
-DumpShaders` to collect paired geometry shaders. `-VertexFetch baseline` and
`optimized` select the individual paths; normal play leaves comparison and dumps
off. `tools/benchmark_gpu_path.ps1` accepts the same vertex selections. Replay
tools accept a trailing `--vertex` while retaining their pixel-shader defaults.
