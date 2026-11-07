# Native GPU constant state and packet decoding — 2026-11-01

## Question and method

Remove measured Xbox command-processing overhead without losing rendering
correctness. The user's subsequent black-flashing report is part of validation.

**[CONFIRMED from the pinned sources]** Identical shader-constant writes still
invalidate host constant buffers, and ordinary PM4 type-0 packets dispatch each
constant word individually. Parts of the observed D3D12 demo write two to three
million individual constant words per second.

The patched D3D12/Vulkan backends now:

- compare native register snapshots with incoming big-endian words and skip
  bit-identical float/bool/loop updates; integer/SIMD comparison preserves NaN
  payloads and signed zero;
- bulk-decode sequential type-0 packets wholly inside pure constant ranges,
  using existing backend range writes and split ring-buffer reads;
- build changed float-vector masks before updating the register snapshot and
  invalidate buffers only when a changed vector is used by the current shader.
  Existing initial/frame invalidation and shader-layout handling remain active.

Payload size, sequential mode, word-aligned ring offsets/capacity and complete
constant-range bounds are checked. Repeated-register writes and mixed ranges
retain the original decoder. Texture/fetch, scratch/event, coherence/readback,
occlusion and ordering behavior are not bypassed. This is native host state
processing, not an engine-specific renderer or a removal of shader semantics.

Helpers live under `port/src/` and `port/sdk_patches/`.
`tools/prepare_native_gpu_sdk.py` derives original GPU sources from Git and
requires each current file to be original or the exact expected patch. It
validates all affected sources before writing. The outer SDK preparation
requires revision `bd833a2ab69d305f99ddf57418fc38ffec8af93d`.

The source-built dual-backend SDK enables `ch2k8_native_constants` and
`ch2k8_native_packets` by default. Their `--no-` flags restore original paths.
`ch2k8_gpu_stats` and randomized `ch2k8_packet_compare` are opt-in, off normally.
The original binary-only D3D12 SDK does not gain these controls from a game-only
rebuild. The launcher prefers the dual build when present.

## Evidence: correctness

**[CONFIRMED]** Tests cover 2,049 constant lengths, changed first/middle/last
words, special float encodings, register boundaries, overflowing ranges, guarded
page tails, partial-vector changes and vertex/pixel bank crossings.

**[CONFIRMED]** 12,288 original/native packet comparisons execute extracted
decoder methods with the actual SDK ring buffer. Register results, read offsets
and modeled non-constant event counts match. Coverage includes wrapping,
unaligned offsets/capacity, repeated-register mode, cross-boundary ranges and a
truncated payload. Patch idempotence and rejection of local changes are tested.

Both Release game builds and the patched GPU plugin build pass. Full suite:
**74 passed, 1 skipped** (separate PS3 extraction absent). Launcher argument and
layout checks pass. Native-image summaries now detect completely black RGB
output, ignoring alpha; image presence alone is not rendering validation.

## Evidence: constant cache

Runs `20261101-094819-478-gpu-d3d12-rov` (baseline) and
`20261101-095241-732-gpu-d3d12-rov` (cache) use identical executable/GPU DLLs.
Bulk type-0 decoding is not yet present in that DLL. Seconds 120–180:

| Measurement | Baseline | Cache |
|---|---:|---:|
| Individual write requests | 152,964,464 | 134,396,824 |
| Range write requests | 528,508 | 494,581 |
| Skipped requests | 0 | 82,667,543 |
| Float-buffer upload requests | 2,483,426 | 1,098,735 |
| Median guest interval | 55.256 ms | 55.364 ms |

The cache skips **61.3%** of its requests. Different demo scenes/request counts
prevent treating the upload totals as a controlled reduction ratio. There is
no demonstrated whole-game speedup. Cache readback shows coherent live play at
**4:03**, 0–0, with court and HUD visible.

## Evidence: interleaved bulk decoder

`20261101-100214-095-gpu-d3d12-rov` randomly interleaves eligible packets within
one process, with caching enabled for both. Seconds 120–180:

| Path | Packets | Words | Measured time | Mean ns/word |
|---|---:|---:|---:|---:|
| Per-word | 1,463,362 | 59,351,088 | 455.400 ms | 7.673 |
| Native bulk | 1,462,628 | 59,422,952 | 132.179 ms | 2.224 |

**[CONFIRMED in this workload]** Decoding time per word falls about **71%**.
The scope includes backend constant handling, not just byte conversion.
Scheduling, packet-size distribution, timer overhead and cache state limit
interpretation. This is not a 71% FPS gain. Median guest interval remains
**55.228 ms**; readback shows coherent live play at **4:03**, 2–2.

## Black-flashing investigation

The user reports black flashing during default-enabled Vulkan FBO run
`20261101-100939-644-gpu-vulkan-fbo`. Its 120-second image is coherent live
play, but the 180-second image is entirely black, including the HUD. Only one
earlier placeholder-presentation skip is logged; that does not explain the
later black image. The run is stopped in response to the report.

Isolation run `20261101-101503-978-gpu-vulkan-fbo` disables **both** new
optimizations in the same executable/GPU DLL. Its 180-second native image is
also completely black. The new paths are therefore not required to trigger
the failure. This does not identify the underlying surface/resolve bug, and
the demos are not identical workloads. Earlier good snapshots did not establish
general FBO compatibility.

Run `20261101-101909-021-gpu-vulkan-fsi` retains both native optimizations at
their enabled defaults, without interleaving. Native images show a coherent
introduction and later live play at **4:22**, 0–0. Neither sample is black;
98.8% of the later image has nonzero RGB. Seconds 120–180 record:

- **167,013,496** eligible words handled in bulk and zero individual constant
  write requests;
- **44.1%** of range requests skipped as redundant;
- **2.300 ns/word** bulk decoding and **55.542 ms** median guest interval.

These samples validate this bounded FSI demo, not an uninterrupted display
trace or full match. Exhibition/replay/camera transitions, Legacy/save stability
and the UGA black-head issue remain open.

Later process CPU accounting is about 1.56 cores in the ROV baseline and 1.64
in the FSI run. The earlier observation of roughly half as much CPU usage on
Vulkan does not repeat here; it must not be presented as a backend reduction
ratio. Scene and host/driver state still limit those comparisons.

## Launcher and build correction

The launcher offers **Automatic**, **Native render targets**, and **Accurate
Xbox blending**, saved with successful launch choices. Native selects RTV/FBO
and explicitly warns about experimental black flashing. Automatic now chooses
D3D12 ROV or Vulkan FSI; Accurate explicitly chooses the same compatibility
paths. Renderer, resolution, refresh and window controls remain available.
The revised launcher layout was rendered and visually inspected.

An initial run used a stale GPU DLL because the SDK staged plugins only when
the executable relinked. That run is marked invalid and excluded.
`port/CMakeLists.txt` now makes linking depend on the runtime and GPU DLLs,
triggering staging when either changes. Installed/staged hashes match after
rebuilds. No game assets, generated sources, raw captures or binaries are committed.

## Conclusion and remaining work

Native state caching and bulk decoding remove measured Xbox CPU command
overhead while preserving fallbacks. Overall submission cadence still needs
work. Fixed-function native targets cannot safely replace compatibility pixel
operations everywhere yet: black rendering reproduces without these new
optimizations. Further GPU-specific removal needs the failing surface/pass
dependencies identified before changing format/blending/resolve semantics.
All bounded game and telemetry processes started for these tests have stopped.
