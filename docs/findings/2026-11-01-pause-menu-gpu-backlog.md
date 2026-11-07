# 2K Nav pause-menu slowdown

## Question

Why does opening the in-game pause menu cause extreme lag, and which work should be optimized?

## Method

Capture the actual menu left open by the user, then separately time native synchronization scopes during an ordinary D3D12 ROV run. All GPU capture, bytecode and telemetry remain local. The new scopes are enabled only with `--ch2k8_gpu_stats`; they preserve all original waits and barriers. Aggregate durations on the graphics thread separately for idle command rings, WAIT_REG_MEM and submission fences. Detailed wait logging is rate-limited to one slow packet per second.

## Evidence

**[CONFIRMED]** Local `20261101-191526-860-capture-optimized/nav.rdc` records the visible pause menu over Georgia gameplay. There are 3,057 indexed draws and three other draws, two native command-list submissions, 338 recorded barrier calls, and 548 pipeline bindings. AMD GPUTime returns 3,387 actions totaling about 27.0 ms. The leading individual draw is event 8503, around 0.742 ms. These instrumented per-action costs omit other execution/serialization costs and must not be substituted for live frame duration. The frozen background is still redrawn.

**[CONFIRMED]** Ordinary run `20261101-192802-503-gpu-d3d12-rov` reaches the same visible pause-menu state. Between elapsed 160 and 270 seconds, 1,032 guest submissions have a median interval of **115.181 ms**. Median native submission-fence scope occupancy is **71.72%** of its one-second reporting window; register waits occupy **8.79%**. AMD reports approximately 96-99% graphics activity near 2,707 MHz. Guest VdSwap itself costs roughly one microsecond. This is a native GPU backlog, not slow VdSwap or the previously observed animation packing hotspot.

A separate bounded 300-round sample of the original paused run finds a busy guest thread concentrated in `FUN_84DCA290` (175 attributed observations), `FUN_84DDA4D0` (52) and the small TLS accessor `FUN_84E04948` (21). Original instructions in the first two repeatedly check shared counter values and wait progress. **[LIKELY]** These are guest-side polling paths; no broader engine-purpose names are assigned. The native fence timings provide the stronger attribution of the downstream stall.

The same run's startup instead has negligible submission-fence time and nearly a full second per second in register waits. Detailed packet logging identifies memory equality waits at physical address `1FCA3006`, reference zero, full mask, interval `0x100`; they commonly last about one refresh interval during startup. Seeing register-wait samples alone does not prove abnormal pacing.

**[LIKELY]** ROV software depth/MSAA processing and high draw count contribute to the pause scene's GPU cost. The captured shaders still test a dynamic early-depth-write hint separately for each sample even though the hint is constant for a draw. An exact-state specialization was evaluated below. This evidence does not justify removing synchronization or replacing query results with guessed values.

## Validated early-depth improvement

**[CONFIRMED]** The manually operated candidate run `20261101-194654-776-capture-optimized` uses a file-triggered five-second device capture, started only after the user confirms the menu is open. A one-host-frame attempt had captured only a presentation copy, so it was not used for shader timing. The longer capture contains 72 pixel shader resources, including candidate `dff88348`, an exact instruction match for the original menu shader `4a52420e` apart from intended flag operand substitutions. No unrelated sample/format variant is substituted.

Add the draw's exact early-depth-write hint to the existing six-bit depth key by encoding enabled depth separately from disabled depth. Two uncommon combinations keep the original dynamic path; there is no guessed state or shader-hash routing. The hint follows the original alpha-test/alpha-to-mask condition. The per-draw runtime check now independently validates all seven depth/stencil/hint bits. This removes dynamic early-write decisions for each sample and permits driver optimization without dropping any draw, barrier, query or synchronization.

With the user-operated game closed, replay the **original** menu recording, replacing only shader resource `4a52420e`. Full nonzero 10 MiB EDRAM is byte-identical at events **3532, 682 and 12264** before timing. Warm both variants and alternate three measured pairs:

| Trial | Original GPU action sum | Candidate action sum | Event 682 original/candidate |
|---|---:|---:|---:|
| 1 | 27.979 ms | 25.799 ms | 0.14028 / 0.12964 ms |
| 2 | 27.597 ms | 25.596 ms | 0.14108 / 0.12968 ms |
| 3 | 27.042 ms | 25.633 ms | 0.14104 / 0.12952 ms |

Median action-sum reduction is **7.25%** across the same 3,387 timed actions. The selected draw falls **8.08%** (median paired reduction). This is an incremental improvement over the prior depth-specialized shader, not a comparison with the original fully dynamic implementation. It does not establish a corresponding displayed-FPS gain, nor remove the whole native GPU backlog.

## Conclusion and confidence

The observed menu lag is predominantly GPU completion latency. The measured scopes distinguish this state from startup refresh pacing and CPU-bound live gameplay. The early-depth change measurably reduces one recurring shader family's GPU cost with identical captured output, and is enabled together with the independently reversible native depth specialization. A complete pause-menu fix is not yet established.

## Open questions

Determine how much native ROV serialization remains after shader simplification. The apparent frozen court could eventually permit background reuse, but no game-specific pause detection or skipped draw is implemented without a rendering-dependency proof.

## Validation and reproduction

Both Windows Release builds pass, and the pinned dual-backend SDK builds and installs. The repository suite passes **90 tests, one environment-dependent skip**. Key tests exercise 524,288 interpolation round-trips and all 128 seven-bit depth patterns, including reserved dynamic fallbacks. Checked source preparation upgrades the published pixel patch and rejects unknown edits before writing.

Use `capture_gpu_workload.ps1 -ShaderState optimized -ManualTrigger -GpuStats -DurationSeconds 600`, navigate manually, then create the run directory's empty `capture.trigger` file. The five-second device capture spans host presentation calls. `--ch2k8_gpu_stats` enables optional one-second wait summaries; detailed wait records are rate-limited. Neither the trigger nor these timers sends game input. Close the game before measuring replay GPU costs. The existing `--no-ch2k8_native_depth_state` fallback restores dynamic depth/hint handling; the general pixel-state fallback remains available.

## Subsequent resolution

The [native pause-menu fix](2026-11-01-native-pause-fix.md) supersedes the open lag conclusion above: the user validates responsive menus and no flashes with native D3D12 and bounded ownership extents, including their ordinary 1440p borderless launcher. The shader measurements here remain separate historical controls.
