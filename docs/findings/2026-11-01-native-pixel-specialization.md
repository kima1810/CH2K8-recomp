# 2026-11-01: Exact-state native pixel shader specialization

## Measured graphics bottleneck

**[CONFIRMED]** Fresh D3D12 ROV capture
`20261101-141118-gpu-capture/device_capture.rdc` contains 40,023 timed actions.
The largest measured draws again use host pixel shader hash `785f762a` and
vertex shader hash `d553244a`, at a 640x360 viewport. These are native shader
hashes, not recovered engine-purpose names. The original shader contains
generic Xbox EDRAM addressing, sample, format, depth/stencil and blending code.
Its engine pass purpose remains unidentified.

The local capture SHA-256 is
`ffbf75208c5c74eb57eb361f0bc827f584beb0a88ea662dcd38e539a5625baae`.
All captures, exported shader binaries, disassembly and raw buffers remain in
ignored local output directories. No game-derived shaders are committed.

## Change

**[CONFIRMED]** The patched source SDK specializes D3D12 ROV pixel shaders to
the exact current draw state. A 16-bit field in the existing 64-bit shader
modification key encodes:

- the MSAA sample mode;
- depth format and alpha-test comparison bits;
- render-target 0's color format;
- an exact reversible index for 31 known symmetric color/alpha blend controls,
  or a dynamic fallback marker for all other controls.

The translator substitutes immediate values only for those exact operands.
The native driver can eliminate irrelevant format switches, blend-factor and
blend-operation branches, MSAA choices, and depth-conversion paths. Existing
arithmetic, precision, sample coverage and memory ordering remain intact.
Other render targets, unfamiliar/asymmetric blending, gamma flags and other
unencoded state retain their original dynamic paths. Vertex shaders and host
RTV shaders retain their original paths. Vulkan SPIR-V is not changed here.

No scene assumption or hardcoded shader hash selects these optimizations.
Every key represents actual register state; changes select distinct cached
variants. Pipeline storage is versioned to reject incompatible older keys.
Before issuing each specialized draw, the command processor verifies the
encoded values against the original system constants, including used RT0
format/blending. A mismatch logs an error and rejects that draw.

`tools/prepare_native_shader_sdk.py` checks all three affected source files
against the pinned originals or exact reviewed patch before writing them.
`prepare_vulkan_sdk.py` applies it during normal SDK preparation. The installed
dual-backend SDK enables `ch2k8_native_pixel_state` by default; the restart-only
fallback is `--no-ch2k8_native_pixel_state`. This control is not in the older
binary-only SDK. Normal ROV/FSI launcher selection remains unchanged.

## Controlled results

Different autonomous demos produce misleading timing ratios: an early
specialized capture appeared much faster, but it was a different scene.
Instead, export the specialized native shader and replace only its original
counterpart while replaying the **same original capture**.

`tools/renderdoc_shader_compare.cpp` requires identical complete 10 MiB EDRAM
contents at events 55097, 37811 and 165644 before timing. It warms both variants
and alternates order over three measured pairs. It uses the adapter's advertised
AMD `GPUTime` counter only after verifying seconds/double/eight-byte metadata.
It does not change stable-power/developer settings. Counter rows must contain
matching action sets; `summarize_shader_comparison.py` rejects malformed pairs.

All three candidates pass those byte-identical EDRAM checks:

| Candidate | Leading draw reduction | Entire capture action-sum reduction |
|---|---:|---:|
| Sample/depth-format/alpha/gamma constants | 3.35% | 1.05% |
| Add RT0 format and identity blending | about 12.3% | about 3.7% |
| RT0 format plus exact common blend controls (final) | **27.27%** | **8.77%** |

The final candidate is exported from
`20261101-144334-914-capture-optimized`, host shader hash `27bff0da`. Its native
readback shows coherent live play at 4:21, and runtime validation logs no
specialized-state mismatches. The preceding format-only capture also renders
coherent live play at 3:53. These bounded demos do not establish full-match,
Legacy, save, replay, camera-transition, or UGA-head compatibility.

Final same-capture counter pairs:

| Trial | Original leading draw ms | Specialized ms | Original sum ms | Specialized sum ms |
|---|---:|---:|---:|---:|
| 1 | 3.226520 | 2.345160 | 475.870080 | 434.191520 |
| 2 | 3.227480 | 2.348960 | 475.918200 | 434.190280 |
| 3 | 3.228840 | 2.348480 | 476.267560 | 434.138520 |

A repeat with the finalized tool additionally rejects all-zero EDRAM snapshots.
All three nonzero buffers still match exactly. The repeat measures about 27.3%
less leading-draw time and 8.6% less summed GPU action time across the three pairs.

**[CONFIRMED]** This is a substantial GPU-cost reduction for the measured
shader on identical recorded work. Only one shader is replaced in this offline
comparison, while the live implementation specializes all eligible shaders.
GPU action sums exclude gaps/synchronization and are not displayed FPS or a
whole-game speedup percentage. Existing CPU vector processing can still gate
the live frame loop. The known FBO black-frame issue is not fixed by this work;
experimental native render-target modes remain opt-in.

## Normal rendering control

The final enabled run `20261101-145159-783-gpu-d3d12-rov` and disabled control
`20261101-145703-123-gpu-d3d12-rov` use identical executable and GPU DLL hashes,
without RenderDoc or per-routine hot logging. Both retain the earlier CPU RAM
optimization. Seconds 120–180 record:

| State specialization | Median guest interval ms | p95 ms | Submissions |
|---|---:|---:|---:|
| Enabled | 40.583 | 49.117 | 1491 |
| Disabled | 40.511 | 49.270 | 1475 |

Both runs produce nonblack live-game images, and the enabled run has no
specialized-state mismatch logs. Scenes are not locked. **[CONFIRMED]** No
whole-game frame-rate improvement is established by this control. In particular,
the earlier 51.346 ms CPU-profiled run must not be used to claim a 20% frame
gain from this GPU patch. Process CPU accounting is similar between these two
runs; earlier cross-run CPU ratios are not attributable to this specialization.
**[LIKELY]** The remaining translated CPU work is still a main cadence limit.
The verified GPU savings create headroom but do not establish consistent high FPS.

## Reproduction tools

`tools/capture_gpu_workload.ps1` launches RenderDoc and only its own checked
game process, records binary hashes and arguments, captures without user input,
saves a native image and stops at its deadline. It validates capture-delay
bounds and offers a side-effect-free `-ValidateOnly`. Example:

```powershell
./tools/capture_gpu_workload.ps1 -ShaderState optimized -DelaySeconds 150 -DurationSeconds 220
```

The native tools are built by `build_renderdoc_tools.ps1`. `shader_probe`
exports only local native shader bytes and bounded root-buffer data; the
comparison tool aborts before timing if EDRAM differs. The ordinary backend
benchmark also accepts `-PixelState baseline|optimized` for uninstrumented
game runs.

The suite passes **87 tests, one environment-dependent skip**. New checks cover
all 32,768 unique full state keys, exact palette reconstruction, state/bitmask
folding, supported swizzles, source-patch idempotence and refusal to overwrite
unreviewed changes, bounded capture argument validation, and paired-counter
aggregation. The pinned dual-backend SDK, both Windows Release game builds and
all five native RenderDoc clients build successfully.
