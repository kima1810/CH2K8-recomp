# Native presentation pacing and the unoptimized Release build

## Two separate causes

Continuing the graphics-backend investigation found two substantial costs that
shader simplification alone could not remove:

1. The DXGI UI tick thread treated every successful `WaitForVBlank` return as a
   real display refresh. In this environment the call succeeds almost immediately.
   This produced over a million false ticks and roughly 9,000 redundant host
   presents per second, even while the game published only one or two frames.
2. The current game build was named **Release**, but its generated compiler
   commands contained no optimization option. `CMAKE_CXX_FLAGS_RELEASE` was empty,
   and the generated SDK project helper did not add a target-level alternative.
   The SDK DLLs were optimized; the recompiled game and native host glue were not.

The earlier 600–700 ms live submission intervals therefore did not establish an
expensive lighting shader. Opt-in scope timings put normal frame publication
below a few milliseconds while presentation spun, and sampling after removing
the spin found 199/200 guest-worker observations in translated game code. The
three previously identified packed-vector routines and their helpers dominate
those observations.

## Presentation fix

The normal blocking DXGI path remains unchanged. Three consecutive waits shorter
than one eighth of the monitor period, capped at one millisecond, identify the
false-success condition. The thread then uses an interruptible monotonic timed
condition wait at the current monitor's refresh rate. This machine reports
180 Hz. The wait releases the mutex, handles shutdown/output replacement, avoids
catch-up bursts, and resets detection for a new output. A completion for an old
output cannot reset or signal a replacement output.

Guest rendering, guest timing, frame publication, swap-chain parameters, texture
quality, lighting, geometry, render-target resolution, and depth/blend behavior
are not reduced or bypassed. This limits redundant host/UI redraws; it does not
cap guest frames below the display rate. Immediate guest-output paint requests
retain their existing handling. `--no-ch2k8_native_present_pacing` retains the
old DXGI behavior for diagnosis. The adaptive path is enabled by default.

`--ch2k8_present_stats` records opt-in wall/CPU scopes for UI ticks, native VBlank,
painting, mailbox acquisition, frame refresh/publication, allocator fences, queue
submission and DXGI Present. Normal play leaves these timings off. Nested scopes
overlap and must not be summed into a frame duration. CPU counters are coarse.
`tools/summarize_present_stats.py` keeps stage/thread attribution separate.

## Release configuration fix

`port/cmake/Ch2k8BuildOptions.cmake` explicitly applies `-O2` and `NDEBUG` to
Release/RelWithDebInfo generated game code and host targets. MinSizeRel uses
`-Os`; Debug retains its unoptimized behavior. The contract also retains strict
floating-point behavior, preserves signed-integer wrapping with `-fwrapv`, and
disables strict-aliasing assumptions. No fast-math,
extra host-only ISA, guest logic rewrite or disabled memory watch is involved.

Before, the relevant Clang compile command contained only the language/runtime,
SSE4.1, asynchronous-exception and line-table settings, with no `-O` option.
After, the same generated target also contains:

```text
-DNDEBUG -O2 -fwrapv -fno-strict-aliasing -ffp-model=strict
```

Tests configure all four build types with deliberately empty global flags and
inspect the resulting commands for both host and guest targets, then execute a
signed-overflow boundary check. An additional
check inspects the actual configured game's rules. Geometry pack, unpack and
guarded-memory checks also run with the production Release policy.

## Measurements and limits

All captures, binaries, source-derived data and detailed logs remain ignored.
These 200-second D3D12 native-target runs retain 1280x720, bounded ownership
extents, synchronous shader creation, and the same visual configuration.
The measurement window is seconds 120–180. Autonomous teams/cameras differ;
submission cadence is not unique displayed FPS.

| Test | Median guest interval | Submissions in window | Mean process CPU cores |
|---|---:|---:|---:|
| Unoptimized, original presentation | 685.536 ms | 92 | 3.563 |
| Unoptimized, paced presentation, hidden | 621.956 ms | 98 | 1.604 |
| Unoptimized, paced presentation, visible | 622.155 ms | 98 | 1.609 |
| Optimized Release, paced presentation, visible | 26.457 ms | 2,202 | 1.872 |
| Optimized Release, original presentation, visible | 45.558 ms | 1,292 | 3.395 |
| Final optimized Release with signed wrap, paced, visible | 25.910 ms | 2,408 | 1.918 |

The first two samples report GPU-activity sensor medians of 68 and 2 respectively.
The counter is raw vendor telemetry, not a calibrated per-frame GPU duration.
The low activity after fixing presentation also reflects the still-slow
unoptimized guest feeding the GPU. The optimized visible sample reports 43.5
activity while actually producing many more frames. GPU/runtime DLL hashes are
unchanged between the visible unoptimized and optimized game samples.

The optimized visible run's median submission rate is 37.8 Hz versus 1.6 Hz in
the unoptimized visible run. The large change is consistent with restoring
compiler optimization, but the unmatched scenes do not support an exact causal
FPS multiplier. Native readbacks show coherent live play at a 3:51 clock, with
court, crowd, players, lighting, shadows and overlays. No rendering settings were
lowered to obtain these results.

The final signed-wrap build completed another 200-second visible run: median
25.910 ms (38.6 Hz), p95 26.309 ms, with 2,408 submissions in the measured window.
Its native readbacks retain coherent player detail and live gameplay.

The old benchmark always launched a hidden window. `-Visible` now makes normal
windowed testing explicit and the JSON records `visible_window`; summaries carry
that field through. Both hidden and visible paced controls were measured rather
than assuming hidden-window behavior explains the whole slowdown.

## Validation and remaining work

The full backend suite passed 163 tests with one skipped. After adding explicit
signed-wrap semantics, all 13 focused build, numeric, memory and presentation
checks passed again, including execution of the signed-overflow boundary test.

The production VBlank thread body is executed against fake DXGI outputs to test
immediate-success detection, genuine blocking waits, output changes, stale failed
completions, shutdown and the disabled fallback. The pure timer is exercised at
24–1000 Hz, including invalid refresh values and late-wakeup handling.

These fixes substantially reduce backend waste and restore optimized guest
execution. They do not establish consistent 60 FPS, full-game completion, or
performance on older physical GPUs/CPUs. The remaining CPU geometry jobs still
need native algorithm and batching work. Hardware qualification must use real
older systems and equivalent scenes, rather than extrapolating activity counters.

Diagnostic commands:

```powershell
tools/benchmark_gpu_path.ps1 -Profile d3d12-rtv-extent -ShaderCompilation synchronous -GpuStats -PresentStats -Visible
tools/benchmark_gpu_path.ps1 -Profile d3d12-rtv-extent -ShaderCompilation synchronous -GpuStats -PresentStats -Visible -PresentPacing baseline
python tools/summarize_present_stats.py RUN/runtime.log --after-seconds 120
```
