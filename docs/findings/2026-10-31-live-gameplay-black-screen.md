# 2026-10-31: Live gameplay black screen

## Question and observed behavior

After packed-vector fixes, the user reports correct rendering in camera
settings and replay, but a black screen in live on-court gameplay. The supplied
pause screenshot shows a coherent court, players and crowd. Game startup is
also laggy, with several seconds of black output. These observations are
**[CONFIRMED]** as user-reported behavior, not an independently reproduced trace.
The user clarifies that gameplay continues while the entire image, including
the HUD, is black. An earlier answer saying the HUD was visible was explicitly
corrected. Do not narrow this to court geometry or claim controls stop.

`ch2k8_010.log` starts at 13:28:55 and closes normally at 13:31:14. There is
no fatal callback error in this attempt. Cached shaders translate in 4 ms and
259 cached pipelines initialize in 23 ms; these startup cache timings do not
measure new pipelines, game-data loading, or the transition into gameplay.

## Method and hypotheses

The visible paused scene establishes that some scene rendering works; it does
not prove the live camera, live rendering passes, or final output are correct.
Neither missing assets nor a complete GPU failure is established.

Two bounded runtime comparisons are prepared:

1. `rov`: set only `render_target_path_d3d12=rov`, retaining the other settings.
   This compares pixel-shader interlock with the default host render targets
   on the user's AMD adapter. It may be slower and is a diagnostic, not a
   performance recommendation or a proven fix.
2. `synchronous`: disable only asynchronous shader compilation. The inspected
   D3D12 command processor skips a draw while an asynchronous pipeline handle
   has no ready pipeline state. This can explain temporary missing output,
   but has not been shown to explain persistent black live gameplay. Blocking
   compilation may increase stalls.

`baseline` applies neither override. All profiles use the same user-data and
cache location, preserving saves. Warm caches can affect later comparisons;
keep the matchup and camera consistent and record cold/warm conditions.

## Instrumentation and validation

`tools/launch_render_diagnostic.ps1` creates timestamped run folders under
`port/out/render-diagnostics/` containing the executable SHA-256, arguments,
runtime log and sampled process CPU time/memory/thread counts. CPU samples
are not GPU frame times or proof of the bottleneck. No shader caches are
deleted and no save files are reset.

The pinned release SDK recognizes `perf_log_csv`, but the initial smoke test
produced no CSV. Its performance-counter frame writes are guarded by a build
option disabled in Release, and the inspected source does not connect that
flag to opening the CSV. Consequently the diagnostic uses independent process
samples rather than claiming frame counters are available.

The app now logs effective GPU settings after plugin registration, allowing
each profile to be verified. A 15-second hidden ROV startup test stayed alive
until deliberately stopped and logged `render_target_path_d3d12=rov` with
async compilation still true. This does not validate live gameplay output.
The host rebuild succeeds. A separate GUI-subsystem stub verifies the launcher
under Windows PowerShell: paths with spaces remain intact, the requested
profile is passed, process samples are written, and normal exit is awaited.
No full gameplay simulation or measured performance improvement is claimed.

## Initial conclusion, before interactive ROV validation

The earlier geometry corruption has improved in the supplied paused view.
Persistent black live output and startup stalls remain unresolved. The first
interactive comparison is ROV; its result determines whether to investigate
render-target handling or continue with camera/output-state and pipeline
timing evidence. Do not combine overrides before isolating their effects.
Since the HUD also disappears while gameplay continues, investigate shared
output and full-screen passes alongside scene/camera state; this observation
alone does not identify a defective pass or prove a GPU-backend bug.

## User validation: ROV restores live gameplay

The user subsequently confirms that the render-test profile renders live
gameplay, replay and camera edits correctly, but runs slowly. One player's
head renders completely black. The supplied screenshot shows a coherent
court and players, though its paused state cannot alone prove moving gameplay.
The interactive gameplay result is **[CONFIRMED] by user report**.
On follow-up, the user identifies the affected player as UGA (number/name
unknown) and confirms the black head persists in replay. This separates it
from the live-only black output symptom. The material/texture/shader cause is
not established.

The matching run folder is `20261031-134017-646-rov`. Its manifest records
`--render_target_path_d3d12=rov` as the sole rendering override, with executable
SHA-256 `FEB7D4A4F60A2C8855A51B9C1A779E24A77E564C6D68B5AC9836C7477521CAC2`.
The game closes normally around 13:44:49, approximately 272 seconds after
launch. No new fatal callback failure is observed in the retained log.

530 process samples span 271.716 seconds, with 645.656 total CPU seconds
(about 2.38 logical cores averaged over the whole session) and a peak working
set around 2.16 GiB. These are whole-session process measurements, including
menus and pauses, not frame timings or proof of a GPU bottleneck.

The retained log contains 963 repeated warnings:
`Incorrect resolve sample selected for 4-sample depth: 6, treating like 0`.
This identifies a depth-resolve investigation lead; it does not establish
the cause of the dark head or slowdown. Preserve the warning rather than
suppressing it as a purported fix.

Use ROV as the current working launch configuration. The local normal
launcher now explicitly requests it; the SDK-wide default is unchanged.
The earlier default host-render-target path failed live output, whereas this
ROV run succeeds. This comparison supports investigating render-target/depth
handling, but does not yet isolate a defective register, pass or shader.

Remaining work: measure live frame/GPU timings, compare warm-cache startup,
identify the affected player and whether the head stays black in replay,
then inspect the relevant material/shader/texture path. Full-game completion,
Legacy mode and save/load validation remain unconfirmed.
