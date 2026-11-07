# Rapid lag report: guest timing and adapter selection

The supplied November 6 log selects Intel UHD Graphics (8086:9A60), D3D12
native RTV targets, 1x draw scale, synchronous shader compilation, native
geometry/constant/shader optimizations and native presentation pacing. Cached
pipeline startup takes 25 ms; the log contains no frame-time, CPU-utilization or
GPU-utilization samples. It cannot identify the ongoing bottleneck or establish
an FPS estimate. The screenshot selects windowed 1280x720 at 120 Hz and stores
the game under OneDrive. Neither cloud I/O contention nor a second GPU is proven.
The log predates the native GPU progress-wait configuration entries.

Two concrete implementation issues were found:

1. `video_mode_refresh_rate` was used both for the host fullscreen mode and
   `VdQueryVideoMode`'s guest refresh rate. The graphics system derives its guest
   VBlank timer from that export. Choosing 120 Hz therefore schedules twice as
   many guest VBlanks as the normal 60 Hz mode. This is an unnecessary timing
   coupling, not evidence that every draw or simulation update doubles.
2. Automatic D3D12 adapter selection used the first capable physical adapter in
   legacy DXGI order. It could select an integrated GPU even when Windows ranks
   a second adapter higher for performance.

The prepared SDK now defines `ch2k8_guest_refresh_rate` independently, defaulting
to 60 Hz. The launcher explicitly selects 60 Hz guest timing while retaining the
requested monitor mode. A deliberate direct CLI guest-rate override remains
available. Automatic adapter selection uses `IDXGIFactory6` high-performance
preference; unavailable interfaces retain legacy enumeration. Explicit positive
adapter indices and the WARP option preserve their original enumeration and
filtering. Capability testing and software exclusion remain unchanged.

Startup logs now include the adapter-selection policy, monitor refresh, guest
refresh, explicit adapter setting and VSync. Both modified SDK sources are
validated against the pinned upstream originals before either file is written.
Preparation is idempotent and refuses unknown edits.

Validation: Release SDK/runtime and game builds passed; 15 focused display,
launcher and SDK tests passed. Tests execute the actual patched guest-rate
getter across 60/120/144/240 Hz monitor settings, exercise explicit override and
clamping, verify launcher argument separation and preparation refusal/idempotence.
A 35-second local live smoke launch at 120 Hz host / 60 Hz guest selected the
high-performance enumeration policy, emitted native GPU progress-wait activity,
and exited with code 0 after a normal window-close request. Local diagnostics:
`out/rapid-display-smoke`, `out/rapid-display-tests-final.log` and
`out/rapid-display-*-build.log`.

These checks do not certify an Intel UHD FPS improvement. Retest the updated
complete beta on Rapid's hardware at 720p and export a full report with measured
frame times if lag persists. Do not mix the new launcher with an older runtime:
the separate guest-rate flag requires the updated SDK DLLs.
