# Native ROV depth and stencil specialization

## Question

Can the native D3D12 driver remove more Xbox output-merger overhead without changing depth, stencil, sampling or blending behavior?

## Method

Carry exact normalized per-draw depth/stencil decisions in the DXBC translation key. Six additional key bits are recovered by losslessly encoding the 16 interpolator enable/centroid pairs as ternary digits: off, center, centroid. The resulting 26-bit value preserves every meaningful combination. Vertex and SPIR-V keys remain unchanged; the DXBC modification is still eight bytes. Bump the shader cache version to invalidate incompatible keys.

Depth specialization duplicates the existing color/depth alias rule using the actual format-aware keep masks. The measured first candidate includes depth enable, comparison, writes and stencil enable. Its successor also encodes the exact early-write hint: disabled depth uses code one; enabled depth compresses five decisions plus the early hint, reserving code zero for dynamic fallback. Two uncommon enabled combinations stay dynamic so the code still fits six bits. The successor passes controlled pause-menu output checks and GPU timing; see the [pause-menu finding](2026-11-01-pause-menu-gpu-backlog.md). Before every specialized draw, independently compare the reconstructed flags against the original command processor system constants and reject mismatches. `--no-ch2k8_native_depth_state` restores dynamic depth handling independently of the existing pixel-state control.

## Evidence

**[CONFIRMED]** Candidate shader identification used exact instruction matching against the previous native shader, allowing only the intended flags constant-buffer operand substitutions. No shader hash is used by production routing. In local capture `20261101-181443-460-capture-optimized`, the matching shader is inventory item 9. Live Tennessee/Army demo rendering is coherent, with no specialized-state mismatch logged.

**[CONFIRMED]** On the proven reference capture `20261101-141118-gpu-capture/device_capture.rdc`, both the previous native control shader and the candidate produce byte-identical, nonzero full 10 MiB EDRAM at events 55097, 37811 and 165644 compared with the original captured shader. Then warm both variants and alternate three measured pairs on the same RX 6650 XT workload:

| Trial | Previous native action sum | New action sum | Target draw old/new |
|---|---:|---:|---:|
| 1 | 437.167 ms | 402.509 ms | 2.349 / 1.605 ms |
| 2 | 434.463 ms | 400.765 ms | 2.348 / 1.603 ms |
| 3 | 435.347 ms | 416.141 ms | 2.348 / 1.605 ms |

Median incremental reduction: **31.69%** for event 37811 (24,264 indices), **7.76%** for the 40,023 timed actions in the recording. This is additional to the previously published pixel-state optimization, using its shader bytecode as the supplied control. Action sums exclude gaps and are not displayed FPS. Only one shader resource is replaced in this controlled experiment.

Fresh capture `20261101-175818-496-capture-optimized` returned zero AMD GPU counter values twice despite successful counter enumeration. The known reference still returns all 40,023 timed actions, so no further retries were made on that fresh capture. Diagnostics-only replay now exports the native RenderDoc log before shutdown removes it.

## Conclusion and confidence

**[CONFIRMED]** Exact depth decisions permit substantial additional driver optimization on the tested shader with identical replay output. Enabled by default in the patched source SDK after controlled validation; the original binary SDK is unchanged. All captures, shaders, driver logs and game data stay local.

## Open questions

Whole-game FPS and the separate 2K Nav pause-menu slowdown require live measurements; replay savings alone do not establish consistent 60 FPS. Other depth/stencil combinations have exact key round-trip and live mismatch protection but are not exhaustively GPU-replayed.

The final seven-bit decision encoding is checked with 524,288 interpolator round-trips and all 128 depth/hint patterns. The pause-menu finding records the successor's independent 7.25% reduction in total timed menu actions from replacing one shader resource, with identical full EDRAM at three checkpoints. The full suite passes 90 tests with one environment-dependent skip; both Release game builds and the dual-backend SDK build/install pass.
