# 2026-10-31: Autonomous renderer and guest-frame profiling

## Question

Is the RX 6650 XT insufficient, or is the recompiled/translated execution
path introducing the slowdown? The user operates remotely and cannot press
a capture key. Investigation must not depend on local keyboard interaction.

## Capture and measurement method

Downloaded portable RenderDoc 1.47 from the official release site. The
Windows executable has a valid Baldur Scott Karlsson Authenticode signature.
The downloaded ZIP's measured SHA-256 is
`b51712e58d40066b34ca30c7869d15f72e4b5c001b2d92232f6783a636d5a3c1`.
No system-wide installation or security/driver setting change was made.

Window automation approval timed out; no game inputs were sent. Two scripting
entry-point attempts did not complete. Switched to the supported native
RenderDoc target-control API, checking the target name and exact process ID
without forcing an existing client's connection. This successfully captured
frames remotely. Single-present captures contained only the final screen-copy
draw, despite a correctly rendered on-court thumbnail. Four consecutive
captures had the same limitation.

Added opt-in application-controlled capture using the runtime provider's
D3D12 device. `ch2k8_gpu_capture` supplies a file prefix, and
`ch2k8_gpu_capture_delay` defaults to 120 seconds. A worker records an
approximately 800 ms interval across host presentation boundaries, then saves
the capture. Cancellation joins before device teardown. The normal launcher
does not enable this feature. The official MIT-licensed application API header
is retained under `port/third_party/` with its notice.

RenderDoc's generic D3D12 counter path returned no results. Upstream source
shows that it requires a successful `SetStablePowerState(TRUE)`, otherwise
reporting that Windows developer mode is required. Rather than change that
setting, use the adapter's advertised AMD `GPUTime` counter. The native replay
tool validates floating-point, eight-byte results and seconds units, then
converts to milliseconds. This works on the local adapter.

Raw captures, shader disassembly and game-derived data stay under ignored
`work/` and `port/out/`; none are committed or uploaded.

## Confirmed GPU results

- Single-present screen-copy draws replay in **0.0496–0.0606 ms** at a
  2560×1440 viewport. They do not explain the reported slowdown.
- The full device interval (`device_capture.rdc`, 429,248,902 bytes) contains
  **45,472 timed GPU actions**, including **39,400 indexed draws**.
- Sum of reported per-action GPU times: **288.428 ms**. Indexed draws account
  for **267.714 ms**, dispatches **4.180 ms**, and buffer/texture copies together
  **2.421 ms**.
- The largest measured draw costs **2.046 ms**, uses **21,024 indices**, a
  **640×360 viewport**, pixel shader hash `785f762a`, and vertex shader hash
  `d553244a`. Its pixel shader declares rasterizer-ordered UAV access. The
  precise engine purpose has not been established.
- Fourteen intervals between repeated instances of that scene draw contain
  about **2,996–3,054 timed actions** and summed action cost **18.843–19.889 ms**.

These are offline replay measurements from an autonomous on-court scene,
not a controlled replay of the user's exact Georgia matchup. Summed action
durations exclude gaps/barrier and scheduling costs, and repeated scene
batches are not automatically interchangeable with complete gameplay frames.
Do not equate the earlier 200–250 ms PresentMon records with individual draws,
or conclude that GPU hardware capacity alone is the cause. Conversely, sums
near 19 ms do not rule out expensive synchronization between actions.

## Actual guest submission cadence

Read-only Ghidra confirms `84DCB314` is `bl 84F5A6BC` (`VdSwap`) and
`84DCB318` is the continuation. Two no-argument mid-assembly probes preserve
guest register state and do nothing unless `ch2k8_frame_log` is set. The CSV
records submission interval, probe wall time across VdSwap, and current-thread
CPU time. The interval includes small probe overhead; Windows thread CPU
accounting is coarse, so individual zero CPU entries are not proof of no work.

The uninstrumented-by-RenderDoc baseline run `20261031-193709-900-rov` records:

| Timeline | Median submission interval | Median cadence | VdSwap-site wall time |
|---|---:|---:|---:|
| 0–45 s | 16.706 ms | 59.86 submissions/s | 0.001 ms |
| 60–110 s | 78.355 ms | 12.76 submissions/s | 0.002 ms |

A second baseline run, `20261031-194937-727-rov`, repeats the slow cadence:
**77.925 ms / 12.83 submissions/s** over seconds 60–110. This establishes
that the slow live loop is real and the delay is not spent inside VdSwap
itself. Submission cadence is still not a count of unique displayed frames.

## Named-thread sampling

A 21.5-second live sample finds a guest worker consuming about one CPU core.
Thirty instruction-pointer samples from that worker land primarily in:

- `84723778`: 15 symbolized samples;
- `84723CC0`: 6 samples;
- `84724930`: 5 samples;
- four additional samples attributed to inlined SIMD operations.

These bodies are vector-heavy loops. No speculative animation/skinning symbol
names are assigned. The main guest thread and GPU command thread are mostly
waiting in the sampled interval. Another thread spends its sampled time in
`NtGdiDdDDIWaitForVerticalBlankEvent`; that is an investigation lead, not proof
that vertical-blank handling causes the slowdown. Thread sampling identifies
where execution happens, not automatically which thread gates frame completion.

## Tested optimization hypothesis: AVX2

Preserved the baseline executable/PDB and built only the three containing
translation units with `-mavx2`, excluding their incompatible SSE4.1 PCH. No
FMA or fast-math was enabled. Native disassembly shows AVX2 variable shifts.

The experiment (`20261031-194418-629-rov`) gives **81.205 ms / 12.31 submissions/s**
over seconds 60–110, versus about 78 ms in both baselines. Scene state was not
locked identically, so this is not a precise performance regression claim.
There is **no demonstrated improvement**. The experimental option was removed
and the normal SSE4.1 build restored; experimental binaries remain ignored.

## Live AMD telemetry

Read only `ADL2_New_QueryPMLogData_Get` through the installed AMD driver.
Over seconds 60–124 of the repeat baseline:

| Sensor | Median | Range |
|---|---:|---:|
| Graphics clock | 2693 MHz | 2645–2701 MHz |
| Graphics activity | 75% | 68–95% |
| Edge temperature | 59°C | 58–61°C |
| Hotspot temperature | 67°C | 64–71°C |
| ASIC power | 83 W | 69–85 W |

The throttler-status sensor is unsupported and is not treated as zero.
The measurements do not support an idle/low-clock explanation and the
temperatures do not suggest thermal throttling. No power limits, voltage,
clock settings or Windows developer/security settings were changed.

## Reproducing the tools

`tools/renderdoc_capture.cpp` and `tools/renderdoc_replay.cpp` use the official
native replay headers matching RenderDoc 1.47. Compile on Windows x64 with
`RENDERDOC_PLATFORM_WIN32` and an import library for `renderdoc.dll`; place the
executables beside that DLL. `tools/amd_telemetry.cpp` requires the official
AMD ADL headers and loads only the installed system driver library. The bounded
thread sampler checks the target executable name and thread ownership before
briefly suspending/resuming a selected thread to read its instruction pointer.

`tools/build_renderdoc_tools.ps1 -Headers PATH -RenderDoc PATH -LlvmBin PATH`
builds the three replay clients using matching headers and the portable DLL.
The capture client ignores capture notifications older than its request, since
connecting also announces existing captures. Timestamps have second precision;
avoid connecting immediately after another capture when validating a fresh one.

## RTV extent-estimator hypothesis

The pinned runtime's `draw_extent_estimator.cpp` describes CPU execution of
unclipped vertex shaders as a way to avoid spurious EDRAM ownership transfers
and corruption. Its master flag is disabled by default. This motivates a
**[GUESS]** that enabling `execute_unclipped_draw_vs_on_cpu` could help the
RTV live-black-screen issue.

An instrumented RTV run with this flag enabled records **79.145 ms / 12.64
submissions/s** during seconds 60–110. Its timed device-capture thumbnail shows
a coherent court and players, but the 5:00 clock and introduction overlay do
not establish that the previously failing live-gameplay phase was reached.
A later target-control request initially returned the already-existing device
capture; that thumbnail is not independent evidence. The capture client now
filters old notifications. RenderDoc instrumentation and unmatched scene state
also prevent a precise speed comparison against the native ROV baselines.
There is **no demonstrated performance improvement or verified RTV correctness
fix**, so the working ROV launcher remains unchanged.

The diagnostic launcher now writes `guest-frames.csv`. Summarize a bounded
window with `python tools/summarize_guest_frames.py PATH --start 60 --end 110`.
The normal double-click launcher keeps the working ROV renderer and default
SSE4.1 build; capture/timing probes are inactive there.

## Confidence and remaining work

Captured action costs, repeated submission cadence, instruction samples and
telemetry are **[CONFIRMED]** within the stated workloads. A single root cause
or a verified performance fix has **not** been established. The useful next
targets are live inter-action synchronization/submission costs and the three
hot vector routines with matched-state, bit-exact validation before rewriting.
GPU utilization alone does not justify saying the RX 6650 XT is underpowered.

Validation: Release host rebuild passes; repository test suite **35 passed,
1 skipped** with LLVM available (the skipped archive test requires a separate
PS3 extraction). All three RenderDoc native clients compile against the matching
1.47 headers. The bounded thread sampler and read-only ADL reader were compiled
and exercised locally. No generated sources, captures, executables or game
assets are included in these changes.

### Timeline-counter caution

AMD execution start/end counters are also available. They are collected in
separate profiling passes: subtracting `ExecutionStart` from `ExecutionEnd`
across those passes gives a meaningless elapsed duration. Within one start-
counter series, repeated scene landmarks are about 78 ms apart at the median;
per-action work sums remain near 19 ms. Profiling/replay overhead and gaps
are included in the spacing. This is an additional reason to investigate
submission/synchronization rather than interpreting a sum of draw times as
the full frame cost. It does not isolate a specific bad barrier.

The structured-file inventory includes 5,948 `ResourceBarrier` records and
70,961 root constant-buffer view bindings. Initial-state resource creation
records are also present, so these counts must not be presented as a measured
live allocation rate. Ordering barriers are not removed speculatively.

Sources: [RenderDoc API](https://github.com/baldurk/renderdoc/tree/v1.47/renderdoc/api),
[AMD ADL SDK](https://github.com/GPUOpen-LibrariesAndSDKs/display-library).
