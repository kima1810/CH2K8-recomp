# 2026-10-31: ROV slowdown investigation

## Question and scope

Investigate startup stalls and slow live gameplay while preserving the
user-validated ROV rendering path. No measured performance improvement is
claimed in this first profiling pass.

## Confirmed setup

- The native executable uses CMake Release with `-O3 -DNDEBUG`, not a debug build.
- Host CPU: i7-10700F, 8 cores / 16 logical processors; GPU: RX 6650 XT.
- Portable PresentMon 2.6.0 is downloaded from its official GitHub release,
  not installed system-wide. SHA-256:
  `b2a706bc6ad475749e3b7e3409263aa1e6906d45bdcf993f6dbc0f660188f1af`.
- The capture filters CH2K8; the integrated launcher uses the specific process
  ID and its own named ETW session, avoiding unrelated applications/sessions.

## Measurements and limits

The first capture (`20261031-134952-performance`) contains 24,328 host
presentation records on one swap chain before a new native trap interrupts
the game at approximately 45 seconds. It is **not sustained gameplay evidence**.
The user has not yet identified the precise action at the interruption.

In the PresentMon timeline's 15–40 second window, 7,154 records span 25 seconds:

| Metric | Median | 95th percentile |
|---|---:|---:|
| Host present interval | 5.471 ms | 5.590 ms |
| GPU busy per host present | 0.324 ms | 1.257 ms |
| GPU time per host present | 0.324 ms | 4.440 ms |
| Present API time | 0.046 ms | 0.402 ms |

There are about 286 host presentation calls per second in this window. This
is not gameplay FPS: the presenter can submit repeated images and separate
UI work. Neither these GPU timings nor process CPU averages establish the
on-court bottleneck. In particular, the captured startup window does not
demonstrate GPU saturation.

The inspected SDK presenter explicitly uses DXGI `Present(0, ...)`. It permits
presentation from the guest-output thread, while its UI-thread path has tick
limiting. These are investigation leads, not proof that reducing host presents
will accelerate guest simulation or ROV scene work.

## Profiling blocker repaired

Windows reports C000001D at executable RVA `728961`. PDB mapping and native
disassembly identify a generated `ud2` in `sub_84C1EAA8`, not a GPU-driver crash.
Read-only Ghidra verifies the second dispatch at `84C1EBAC` reads eleven words
at `[84C1EBB0,84C1EBDC)`, but generation emitted only case zero. The remaining
original targets are documented in `control_flow.toml`.

The table is followed by an earlier dispatch's case code before its own first
target. Therefore it is outside the exact self-contained inline-table idiom
recognized by the existing 1,762-table audit. That audit's zero disagreements
did not cover this layout. The final shared epilogue ends at `84C1F038`, where
the next independent prologue begins. Add that function bound and all eleven
table entries; preserve original behavior rather than bypassing the trap.

Native rebuild passes. A generated-output regression checks the owning function,
selector, and all eleven original targets. Full suite: **31 passed, 1 skipped**.
The existing inline audit still compares 1,762 tables without disagreement.
The repaired dispatch needs an interactive retry.

## Reproducible next comparison

The diagnostic launcher now captures PresentMon when the verified local binary
is present, plus process CPU/memory samples. It records trace errors explicitly;
ETW access can require an administrator shell. A restricted smoke test denied
ETW, while an unrestricted smoke test started successfully. No account groups
or machine security settings are changed.

- `-Profile rov`: unchanged working rendering path, now with timing capture.
- `-Profile rov-ui`: keep ROV, change only `host_present_from_non_ui_thread`
  to false. This is an unproven presentation-scheduling experiment.
- Existing `baseline` and `synchronous` profiles remain available; neither
  restores the validated ROV path automatically.

`tools/summarize_presentmon.py` handles BOM headers, unavailable GPU values,
separate swap chains and bounded timeline windows. Its rate is explicitly
labelled host presents per second. Normal launcher behavior remains ROV.

Use the same matchup, camera, window size and warm-cache state. Capture a slow
live segment, then pause and replay, recording the approximate transition
times. Compare GPU busy/wait with CPU/thread activity before changing
readback, memory coherency, assets or graphics correctness settings. Do not
disable required readback merely because it may stall.

## Confidence and outstanding work

Build flags, captured timing statistics and the missing switch entries are
**[CONFIRMED]**. Presentation overhead contributing to the reported slowdown
is **[GUESS]** until a comparable live-game capture shows the effect.
Sustained gameplay profiling and a demonstrated speedup remain outstanding.

Primary tool documentation:
[PresentMon console application](https://github.com/GameTechDev/PresentMon/blob/v2.6.0/README-ConsoleApplication.md).

## Completed user test: startup compilation and long GPU work

The user ran `20261031-185744-266-rov-ui` from 18:57:44 to 19:03:03
America/New_York. The game closed normally after about 319 seconds. The
manifest requests ROV plus UI-thread presentation; runtime confirms ROV,
async shaders enabled, resolve readback disabled and memexport readback enabled.
Executable SHA-256:
`AB24748FD33544221F896393AD44AA62A200E3CA4999E626EB2B21EFAB200471`.

The user reports entering camera settings and doing so before exiting; exact
phase transition times and a subjective speed comparison are not available.
Do not assign specific timed windows to live gameplay or replay without that
evidence.

### Startup cost is directly identified

The runtime reports **232 graphics pipelines created in 30,951 ms**. Cached
shader translation itself takes only **7 ms**. Process samples average about
**9.50 logical CPU cores** over seconds 0–30, falling to roughly **1.3–1.5 cores**
in most later minute windows. Thus pipeline creation is a major confirmed
startup cost in this run. The trace includes a roughly 32-second gap around
that initialization. It does not establish why the driver's pipeline cache
was expensive on this run or prove that pipeline creation causes all later
loading transitions. Disabling preload would risk moving compilation stalls
into gameplay rather than removing the work.

### Later slow periods contain expensive GPU work

The capture contains 54,344 host presentation records on one swap chain.
Whole-run medians conceal the problem because inexpensive UI/repeated-image
presentation records dominate. Use time windows and tail statistics:

| Capture timeline | GPU busy median | GPU busy p95 | GPU busy p99 | Records >=100 ms |
|---|---:|---:|---:|---:|
| 180–240 s | 0.347 ms | 25.915 ms | 227.997 ms | 163 / 4,400 |
| 300–319.2 s | 95.079 ms | 217.987 ms | 227.573 ms | 107 / 275 |

During seconds 180–240, GPU wait p99 is only **0.063 ms**, with a maximum of
**0.108 ms**. Near the end, one GPU-busy record reaches **1,058 ms**. These
measurements identify expensive GPU-associated presentation records, but do
not isolate the critical path of a gameplay frame. They do not identify
individual draws/shaders, distinguish overdraw from bandwidth/ROV ordering,
or constitute gameplay FPS. Presentation scheduling alone has not eliminated
the long GPU work; there is no matched normal-ROV GPU capture proving its
relative speed effect.

### Capture lifecycle and follow-up

PresentMon remained alive with its CSV locked after the game closed. Ending
only its named `CH2K8-4940` session released and flushed the 13.3 MB trace.
The launcher now records trace/game PIDs and the session name in `trace.json`
and adds an independent timed stop (default 600 seconds), so capture lifetime
is bounded even if process-exit cleanup is interrupted. It still requests
termination at game exit and stops only its own session.

The summary tool now reports p99 and >=16.7/100 ms counts; a regression checks
that a rare expensive GPU record remains visible even with a fast median.
The app logs resolution scale, shader flow-control mode, pipeline creation
thread count and presentation-thread setting on future runs.

Next diagnostic target is per-draw GPU timing/capture of an expensive ROV
scene. Keep the working rendering and memory-coherency settings intact.
Changing DXBC control-flow generation is not promoted as an optimization:
[Xenia's upstream implementation](https://github.com/xenia-project/xenia/blob/master/src/xenia/gpu/dxbc_shader_translator.cc)
documents driver-dependent stability issues and recommends switch flow on AMD.
No verified performance fix is claimed yet.

Subsequent [remote device and guest-frame profiling](2026-10-31-remote-renderer-profiling.md)
finds normal GPU clocks, roughly 78 ms submission intervals and roughly 19 ms
summed GPU action cost per repeated scene batch. This narrows the earlier
interpretation: the PresentMon records alone do not establish that the RX 6650 XT
is underpowered, or distinguish CPU, synchronization and GPU execution delays.

Validation of this follow-up: host rebuild **PASS**, full suite **32 passed,
1 skipped**, and the Windows PowerShell GUI-stub smoke confirms trace metadata,
bounded capture options and normal exit handling. Raw captures remain local.
