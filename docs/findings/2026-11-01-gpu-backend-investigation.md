# Native GPU backend investigation — 2026-11-01

## Question

Follow-up: the [native-state investigation](2026-11-01-native-constant-state.md)
reproduces completely black FBO images with both new optimizations disabled.
Earlier coherent snapshots below do not establish general native-target
compatibility. Automatic Vulkan launching now requests FSI. The earlier CPU
accounting gap between APIs also does not repeat in the later runs.

Can native D3D12 or Vulkan rendering remove the remaining lag after the CPU
vector optimizations? Which backend changes are supported by live evidence?

## Existing native paths

**[CONFIRMED from the pinned SDK]** Both backends already issue native host GPU
commands. They retain Xenos command/shader and EDRAM behavior:

| Path | Native implementation | Main compatibility tradeoff |
|---|---|---|
| D3D12 ROV | DXBC, rasterizer-ordered UAVs | Shader code emulates depth/stencil, blending, pixel formats and tiled EDRAM addressing |
| D3D12 RTV | DXBC, host render targets | More fixed-function work; overlapping guest surfaces may need transfers and extent tracking |
| Vulkan FBO | SPIR-V, host render targets | Runtime default; fixed-function rendering with guest format/layout adaptation |
| Vulkan FSI | SPIR-V, fragment shader interlock | Explicit diagnostic selection; shader emulation of guest pixel operations when supported |

Relevant sources are `src/graphics/{d3d12,vulkan}/{command_processor,
pipeline_cache,render_target_cache}.cpp` in SDK revision
`bd833a2ab69d305f99ddf57418fc38ffec8af93d`. Vulkan's empty/default selector chooses
host render targets in this revision; it does not automatically prefer FSI just
because interlock is supported. An unsupported requested FSI path falls back to
host render targets. The RX 6650 XT advertises the required interlock features
in these tests.

[Microsoft's ROV specification](https://microsoft.github.io/DirectX-Specs/d3d/RasterOrderViews.html)
defines ordering of overlapping pixel-shader UAV operations.
[Khronos's fragment-operations specification](https://docs.vulkan.org/spec/latest/chapters/fragops.html)
defines interlock ordering scopes. These mechanisms preserve guest ordering;
simply removing them is not a correctness-preserving optimization.

## Method

Run one game at a time, with the current optimized vector defaults, a 1280×720
guest video/window request and 60 Hz guest timing. Do not disable memexport
coherence, occlusion queries, depth tests or synchronization barriers to obtain
an apparent speedup. Capture the native output at approximately 120 and 180
seconds, then stop the bounded run. No remote keyboard input is required.

`tools/benchmark_gpu_path.ps1` makes these experiments reproducible. It records
the exact executable/arguments, timestamps, intentional-stop status, process
CPU/working-set samples and optional read-only AMD telemetry. Current versions
also hash DLLs beside the executable. Earlier/manual runs do not have every
field. All data remains local under ignored `port/out/render-diagnostics/`.
`-ValidateOnly` checks paths and emits configuration without launching, saving
settings, or creating a run directory.

`tools/summarize_gpu_run.py RUN` summarizes seconds 120–180 by default. Guest
submission cadence is not unique displayed FPS. Autonomous demos choose
different teams/cameras and are **not matched-state benchmarks**. Sensor values
retain the reader's raw names/units; unsupported readings remain null. Pipeline
creation log counts are not pipeline creation durations.

## Evidence

### Vulkan default and fragment interlock

- **[CONFIRMED]** `20261101-090918-163-gpu-vulkan-auto` renders live demo play at
  120 seconds with a visible HUD and 4:55 clock, then 2–2 at 4:00 near 180
  seconds. Median submission interval is **55.177 ms**, p95 **55.491 ms**.
  The initial surface-capabilities error is followed by successful rendering;
  it is not by itself evidence of a persistent backend failure.
- **[CONFIRMED]** `20261101-091736-217-gpu-vulkan-fsi` renders a coherent intro
  followed by live demo play at **4:13**, 0–0, with court/players/HUD visible.
  Median interval is **55.064 ms**, p95 **55.334 ms**. Mean process CPU use is
  **1.529 cores** over the window; peak sampled working set is about **1.47 GB**.
  AMD median raw values: graphics clock **1142.5**, activity **53**, ASIC power
  **17**. Throttler support is unavailable, not zero. These readings describe
  this scene and do not establish a matched energy-efficiency ratio.
- The FSI log records 176 pipeline-creation entries and one skipped placeholder
  presentation across the entire run. They do not establish 176 frame stalls
  or their duration. The Vulkan loader reports an existing OBS implicit layer;
  no layer, driver, power, security or global OS setting is changed.

Both runs remain alive until deliberately stopped after their native captures.
This extends prior Vulkan evidence beyond warmups into live demo gameplay.
Full exhibition completion, replay controls and Legacy/save behavior still
require separate validation.

### D3D12 batching

**[CONFIRMED]** `20261101-091332-730-gpu-d3d12-batched` disables only
`d3d12_submit_on_primary_buffer_end`. Native readback shows live play at **4:05**,
3–2, with a coherent court and HUD. Median interval is **56.789 ms**, p95
**58.189 ms**. The preceding optimized ROV reference measured **57.132 ms** in
a different matchup. This is **not a demonstrated improvement**.

Source confirms both backends normally end an open submission at primary PM4
buffer boundaries when pipeline creation permits. Explicit swap/readback/query
paths can still end submissions. D3D12's end-submission implementation documents
ordering assumptions at `ExecuteCommandLists` boundaries. The existing batching
flag stays diagnostic; no ordering barriers are removed and defaults are unchanged.

### Fixed-function D3D12

**[CONFIRMED within this demo]** `20261101-092138-246-gpu-d3d12-rtv` renders an
intro at 120 seconds and live play with a **4:27** clock and **2–0** score at
180 seconds. The historical live black-screen symptom does not occur in this
bounded demo. This is not proof that the user's exhibition/replay transition
is fixed across teams and cameras.

Median interval is **59.760 ms**, p95 **61.133 ms**. Mean process CPU use is
**3.358 cores**, peak sampled working set about **1.07 GB**. AMD median raw
values: graphics clock **1538**, activity **70**, ASIC power **31**. The native
fixed-function path does not demonstrate a speedup over the working ROV reference
or Vulkan samples. ROV remains the normal D3D12 launcher selection.

### Same-build ROV telemetry reference

**[CONFIRMED]** `20261101-092609-714-gpu-d3d12-rov` uses the same executable
SHA-256 as the FSI and RTV harness runs. Its native readback shows a coherent
in-game close-up, visible HUD, **4:13** clock and **2–2** score. Median interval
is **57.182 ms**, p95 **59.057 ms**, with mean process CPU accounting of
**3.077 cores** and peak sampled working set about **1.25 GB**. AMD median raw
values: graphics clock **2427.5**, activity **79**, ASIC power **36**.

FSI's **1.529 cores** and lower clock/power readings at similar submission
cadence make Vulkan a promising host-overhead/efficiency lead. Different scenes,
shader caches, driver scheduling and transient clocks prevent assigning a
controlled reduction ratio to the backend alone. No direct GPU execution-time
counter was collected in these native runs; activity percentages are not frame
durations. Process CPU accounting includes time in the driver and is not proof
that all charged CPU time performs useful rendering work.

## Native renderer optimization opportunities

The existing [RenderDoc GPU profile](2026-10-31-remote-renderer-profiling.md)
still supplies the direct per-action GPU-cost evidence; it predates the latest
CPU changes and is not a new capture of these demos. Reinspection confirms the
largest sampled pixel shader (`785f762a-1208cafc-03bba1f6-5ae0c027`, a **host DXBC
hash**, not a recovered guest function) declares raster-ordered UAV access and
contains 3,345 numbered static assembly instructions. Its source starts with
EDRAM address calculations, coverage handling and software depth operations.
Static instruction count is not executed instructions or GPU time. Its engine
pass purpose has not been identified, so it is not labeled as a shadow, skinning
or lighting pass.

**[LIKELY]** Specializing a measured expensive shader/pass or fixing render-target
transfer behavior is a better GPU-specific lead than changing the API name.
Any specialization must key all relevant guest state, preserve format/depth/
blend behavior, and be measured against the same captured workload. More shader
variants can also increase pipeline creation costs. The existing pipeline
modification key specializes some inputs; ROV still has substantial dynamic
system-constant handling. No replacement shader is shipped speculatively.

A fully engine-specific native renderer would additionally need identified
draw passes, vertex/index layouts, shader constants, resource lifetimes and
surface dependencies. The current `FUN_` catalog does not establish those
contracts. Merely loading models from folders would not bypass the current
command translation or CPU preparation work.

## Validation, conclusion and open questions

Both Release builds pass; the repository suite has **63 passed, 1 skipped**.
Nine new tests exercise all eight profile configurations, missing-disc failure,
coherence-preserving arguments, unsupported sensors and summary limitations.
The harness successfully executes and stops its own FSI and RTV runs, including
telemetry cleanup. Normal launch settings are unchanged; added runtime logging
records batching, bindless, dynamic-rendering and memexport-fast controls.

Native Vulkan and fixed-function D3D12 both reach live demo play. Current
measurements do **not** establish a GPU speed fix or a 60 FPS native renderer.
Vulkan's lower process CPU observation warrants a same-state backend comparison;
the previously sampled guest vector work can still limit submission cadence.
Whole-match stability, the UGA black-head report, real exhibition/replay/camera
transitions, and a fresh per-action GPU capture remain open. All bounded game
and telemetry instances started for this investigation have stopped.
