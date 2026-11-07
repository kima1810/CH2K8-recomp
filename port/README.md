For beta installation and portable packaging, see [BETA.md](../BETA.md). The distributed launcher uses native `ch2k8_tools.exe` for ISO import and loose asset preparation; no Python interpreter is shipped or required. Python below is developer build/research tooling.

# Building the Xbox 360 recompilation

Folder-based Xbox installations, editable SCNE/ROST components and native D3D12
DDS replacements are documented in [loose assets](../docs/formats/loose_assets.md).
Use the patched source SDK / `win-amd64-vulkan` preset for native DDS support.

Native DDS uploads retain only dimensions, mip count and identity in CPU RAM;
the compressed file payload is released after staging. Resident identity checks
avoid re-reading the file. Superseded D3D12 textures and their descriptors are
reclaimed on texture requests once the submission fence completes, and their
allocation is removed from cache memory accounting. In-flight GPU resources
remain protected. These changes reduce replacement-related RAM/VRAM retention;
they do not establish an FPS improvement or gameplay stability result. See the
[memory-retention checks](../docs/findings/2026-11-02-native-texture-memory.md).

This is an experimental native port. Successful code generation or compilation
does not establish that menus or gameplay work.

The three dominant CPU geometry routines use proved native kernels that batch
independent normalization operations and share validated address adaptation.
Normal play omits per-store diagnostic counters. `--ch2k8_geometry_batch=baseline`
restores the previous RAM kernels; `compare` interleaves the two paths for opt-in
hot-function profiling. The [kernel finding](../docs/findings/2026-11-03-native-geometry-kernels.md)
records complete-job and live measurements, bitwise checks and remaining limits.

The GPU-counter retry loop now uses bounded native progress waits after a short
spin. Both original counter words are rechecked before sleeping; completion,
cancellation and timeout decisions remain in the guest code. This reduces CPU
contention without reducing visual quality. `--no-ch2k8_native_gpu_wait` restores
polling; `--ch2k8_gpu_wait_stats` enables diagnostic timing. An older GPU DLL
without the versioned progress exports automatically retains polling. See the
[GPU wait finding](../docs/findings/2026-11-03-native-gpu-progress-wait.md).

Release builds explicitly optimize both the generated game and host glue, even
if the toolchain leaves `CMAKE_CXX_FLAGS_RELEASE` empty. They retain strict
floating-point behavior, signed-integer wrapping and the existing CPU baseline. Native presentation also
detects immediately returning DXGI VBlank waits and uses monitor-rate timed UI
ticks instead of unbounded duplicate presents. `--no-ch2k8_native_present_pacing`
is the diagnostic fallback; normal blocking VBlank waits are unchanged.
The [presentation/build finding](../docs/findings/2026-11-03-native-presentation-and-release-build.md)
records visible-run improvements, visual checks, test coverage and remaining limits.

Measured integer SIMD packing is enabled for three observed hot guest routines.
It preserves the corrected scalar path and can be disabled with
`--ch2k8_vector_pack=baseline`. `compare` randomly interleaves both versions
within a run; `--ch2k8_hot_log=PATH.csv` records opt-in function timing and work
counts. Summarize a window with `tools/summarize_hot_functions.py`.
The [hot-function finding](../docs/findings/2026-11-01-hot-functions-and-vector-pack.md)
records correctness checks, measured 7–11% per-routine work-cost reductions and
their limits. This is not a claim of the same improvement in displayed FPS.
The address catalog is under `docs/symbols/`; unresolved engine purposes keep
their `FUN_` names. Profiling and image captures remain off in normal play.

SIMD unpacking is also enabled within the optimized path. Use
`--ch2k8_vector_unpack=baseline` to compare against the preceding pack-only build,
or `--ch2k8_vector_unpack=compare --ch2k8_hot_log=PATH.csv` for interleaved timing.
The older `--ch2k8_vector_pack=baseline` fallback still selects the fully retained
original bodies. The [remaining-hotspots finding](../docs/findings/2026-11-01-remaining-hotspots-and-unpack.md)
records the additional measured 3–9% routine reductions and remaining store costs.

Aligned vector byte stores are optimized by default within the combined path.
They retain the original volatile byte widths, address calculation and order;
unaligned stores use the original loop. Use `--ch2k8_vector_store=baseline` to
restore the preceding pack/unpack path, or `compare` for interleaved timing.
The CSV distinguishes `store_optimized`; the summary reports `pack_unpack_store`.
Selecting baseline packing or unpacking also bypasses the store optimization.
See the [aligned-store finding](../docs/findings/2026-11-01-aligned-vector-stores.md)
for the additional measured 14–15% routine reduction and validation limits.

An additional proven-span native RAM path is enabled by default;
`--ch2k8_ram_store=baseline` retains ordered byte stores and
`compare` interleaves both paths. Two routines have statically bounded outputs;
other routines and ineligible memory retain byte stores. Hot logs distinguish
`ram_optimized` and count widened/fallback instructions. See the
[native RAM finding](../docs/findings/2026-11-01-proven-native-ram-stores.md)
for paired timing, memory safety checks, and whole-game measurement limits.

The third hot routine now uses the native path when two reloaded output offsets
pass range/alignment checks. A failure preserves the original byte stores for
the rest of that invocation. `--no-ch2k8_guarded_vector_store` disables only this
addition, keeping the preceding CPU/GPU optimizations enabled. See the
[guarded-vector finding](../docs/findings/2026-11-01-guarded-vector-output.md)
for the paired 17% routine gain, complete context/memory checks and graphics
compatibility measurements. This CPU change applies to both graphics APIs.

## Launcher and Vulkan build

The patched source SDK skips bit-identical shader-constant updates and bulk-decodes
pure constant packets. Both are enabled by default in the dual-backend build.
Their fallbacks are `--no-ch2k8_native_constants` and `--no-ch2k8_native_packets`.
`--ch2k8_gpu_stats` and `--ch2k8_packet_compare` enable diagnostic statistics and
randomized packet timing. Run `tools/build_vulkan_sdk.ps1` to apply the checked
SDK patches; the original binary-only SDK does not contain these controls.
See the [native-state finding](../docs/findings/2026-11-01-native-constant-state.md).

D3D12 geometry shaders also specialize known vertex/index byte order and
read-only shared-memory binding by default. Mixed vertex byte orders retain
dynamic attribute swapping; memory-export draws retain the original geometry
path. `--no-ch2k8_native_vertex_fetch` restores all dynamic geometry handling.
Both APIs use SIMD changed-constant masks and bitset usage intersections for
transform/lighting parameter updates. The original lighting and transform math
is preserved. See the [geometry/constant findings](../docs/findings/2026-11-03-native-geometry-and-constants.md)
for bit-exact replay checks, 29–49% local bookkeeping reductions and the lack
of a demonstrated GPU-time/FPS gain in the tested pixel-heavy workload.

The patched D3D12 ROV backend also specializes pixel shaders to exact MSAA,
depth-format, alpha-test, RT0 format and supported blend state. This removes
generic Xbox shader branches while preserving the existing rendering path.
Exact normalized depth/stencil decisions are also specialized, including the
existing color/depth alias rule. `--no-ch2k8_native_depth_state` independently
restores dynamic depth handling. Full RT0 writes also specialize preservation masks,
with `--no-ch2k8_native_full_write` as an independent fallback. The blend palette
includes exact source-alpha RGB modes with alpha overwrite or accumulation. See the
[depth-specialization measurements](../docs/findings/2026-11-01-native-depth-specialization.md).

It is enabled by default; `--no-ch2k8_native_pixel_state` restores the original
dynamic shader path. Other targets and unfamiliar blend modes retain dynamic
handling. Vulkan is unchanged by this shader optimization. The
[pixel-specialization finding](../docs/findings/2026-11-01-native-pixel-specialization.md)
records byte-identical EDRAM checks and a controlled 27% reduction in the leading
draw's GPU time, not a displayed-FPS claim.

For autonomous GPU comparisons, run `tools/benchmark_gpu_path.ps1 -Profile vulkan-fsi`
from PowerShell. It stops its own game after 210 seconds and records native
images, guest submission cadence, CPU samples and optional local AMD telemetry.
Other profiles include `d3d12-rov`, `d3d12-rtv`, `vulkan-fbo` and explicit
`-batched` experiments; `-ValidateOnly` emits arguments without launching.
Use `-Visible` for normal windowed performance measurements; hidden runs are
marked separately. `-PresentStats` enables opt-in stage timings, summarized by
`tools/summarize_present_stats.py`. These nested timings are not additive FPS.
Summarize with `tools/summarize_gpu_run.py RUN_DIRECTORY`. These demos do not
lock matchup/camera state. See the [GPU backend finding](../docs/findings/2026-11-01-gpu-backend-investigation.md)
for measured results and native-renderer limits.

Open `Launch CH2K8.cmd` in the repository root for renderer, resolution,
refresh rate, window mode and extracted game-folder controls. Automatic D3D12
uses native render targets with bounded ownership extents and synchronous
pipeline creation. Accurate Xbox blending retains ROV for compatibility.
Automatic Vulkan uses accurate FSI blending; its native FBO option remains
experimental following black-frame failures.
Vulkan is an experimental native backend through the pinned
Xenos-to-SPIR-V runtime. Choices are saved after launching in
`port/userdata/launcher.json`.

Build the separate dual-backend SDK and game from a shell with Git, Python,
CMake, Ninja, Clang and the Microsoft build tools available:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/build_vulkan_sdk.ps1
```

The script downloads the exact existing SDK revision and its pinned dependencies,
enables Vulkan and D3D12, and builds `port/out/build/win-amd64-vulkan/ch2k8.exe`.
It preserves `port/sdk` and the original game build. Subsequent game-only builds:

```powershell
cd port
cmake --preset win-amd64-vulkan
cmake --build --preset win-amd64-vulkan --parallel 3
```

The launcher prefers this dual-backend executable for either renderer once
built. `--ch2k8_renderer=vulkan` selects Vulkan explicitly; unavailable backends
fail clearly. For a remote launch without UI:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/launch_ch2k8.ps1 -Launch -Renderer vulkan -Resolution 1280x720 -RefreshRate 60 -WindowMode windowed
```

Resolution sets the guest video mode and startup window, rather than every
internal render target. Refresh rate controls guest timing (60 Hz is the original
setting); exclusive fullscreen also requests the closest supported monitor mode.
Borderless uses the desktop mode. The SDK preparation fixes exclusive refresh
forwarding and materializes Windows Git symlink placeholders in libmspack.
See the [Vulkan finding](../docs/findings/2026-11-01-vulkan-and-launcher.md) for
runtime evidence, remaining limitations and reproducibility details.
Timed native framebuffer captures need no debugger or keyboard input:
`--ch2k8_output_capture=PATH_PREFIX --ch2k8_output_capture_delay=60`
writes a BMP through the active presenter's GPU readback API. Optional
`--ch2k8_output_capture_count=3 --ch2k8_output_capture_interval=60` records
multiple phases; these captures briefly synchronize GPU work and stay off
unless explicitly requested. RenderDoc's Vulkan layer is currently incompatible
with this local capture configuration, so built-in readback is the tested path.

## Prerequisites

- A local USA Xbox 360 disc image. The researched `default.xex` SHA-256 is
  `71e8983d1cc009e485696aad19b5fa4b4661761870e2c8972717b932c1e4be36`.
- Python 3.11+ for disc/archive tools; pytest for the archive tests.
- CMake 3.25+, Ninja, Clang 20+, and Microsoft C++ build tools plus Windows SDK.
- The Windows x64 [ReXGlue SDK nightly-20261002-bd833a2a](https://github.com/rexglue/rexglue-sdk/releases/tag/nightly-20261002-bd833a2a).
  Use `rexglue-sdk-0.10.0.24-dev.gbd833a2-win-amd64.zip`, SHA-256
  `1e19d7ec9be0d9d7e1a0088a34a33b068d4dea520181e81318528ef3b37627e7`.
  Extract its **inner** `win-amd64` directory's contents into `port/sdk/`, so
  `port/sdk/bin/rexglue.exe` exists.

The 2026-10-30 investigation uses Clang 23.1.4, CMake 4.4.4, Ninja 1.13.2,
MSVC tools 14.39.33519, and Windows SDK 10.0.26100.0. This is a tested setup,
not a claim that every combination above the minimum versions works.

## Extract and generate

From the repository root in PowerShell, substituting your own ISO path:

```powershell
python tools/xdvdfs.py 'D:\games\College Hoops 2K8 (USA).iso' extract -o work/ch2k8/XBOX/disc
python tools/ch2k8_archive.py work/ch2k8/XBOX/disc verify
Set-Location port
New-Item -ItemType Directory -Force logs | Out-Null
./sdk/bin/rexglue.exe --log-file logs/codegen.log codegen ch2k8_manifest.toml
```

Extraction never overwrites existing files. Use an empty destination for a new
extraction. ReXGlue accepts the retail XEX directly; a separate decrypted copy
is unnecessary for code generation.

## Configure and compile

Ensure `clang++`, `cmake`, and `ninja` are on PATH. A Visual Studio developer
PowerShell with the x64 C++ environment is appropriate if the compiler cannot
find Microsoft libraries.

From `port/`:

```powershell
cmake --preset win-amd64
cmake --build --preset win-amd64 --parallel 2
```

The initial build compiles about 150 MB of generated C++. Start with two jobs
on a 16 GB machine; one initializer alone generates about 8.8 MB of source.
Do not edit `generated/`: fix analysis in `config/` and regenerate. Generated
files, SDK files, build outputs, logs, and game data are ignored by Git.

The build automatically applies `tools/fix_codegen.py` after code generation.
This narrowly corrects the pinned SDK's invalid 32-bit/44-bit sign-extension
expressions for `vupkd3d128`. It preserves the 64-bit intermediate until the
signed 20-bit lane has been extracted. Numeric regression tests cover positive,
negative, minimum, and maximum lanes. Clang treats any remaining oversized shift
as an error. The correction is idempotent and does not rewrite unrelated code.

`tools/run_codegen.py` preserves the manifest's timestamp when the SDK rewrites
identical content. CMake uses it through a build-directory copy of the generated
SDK boilerplate. It applies the VMX correction before returning to Ninja and
preserves C++ timestamps only when the final corrected bytes are unchanged.
Genuine changes are retained. This avoids making an unchanged project dirty
after every codegen invocation; the original generated boilerplate stays intact.
Windows linking also emits a PDB containing the generated code's line tables.

After a successful build, the executable is `out/build/win-amd64/ch2k8.exe`.
An explicit runtime command is:

```powershell
./out/build/win-amd64/ch2k8.exe --game_data_root ../work/ch2k8/XBOX/disc --gpu_plugin xenos --render_target_path_d3d12 rov
```

ROV is the current user-validated path for live gameplay on the tested AMD
adapter. The default host-render-target path produces black live output even
though replay/camera views render. ROV is slower; performance and one player's
black head remain unresolved. Full-game completion and Legacy are untested.

## Verify and investigate

From the repository root:

```powershell
python -m pytest tests -q --basetemp=out/pytest
Get-ChildItem port/generated/default -Filter '*.cpp' | Select-String 'REX_FATAL'
```

No `REX_FATAL` matches are expected after the control-flow fixes. Switch default
traps still exist; removing known fallbacks is not proof of complete coverage.
The PS3 integration test skips when its local dump is absent. The generated
startup-loop execution test additionally needs Windows, the local SDK, and
locally generated sources; it checks that loop indices 8 and 9 no longer trap.

For executable research, Ghidra 12.2 with Java 25 and the matching Xenon360
0.8.2 extension can import the retail XEX. `ghidra/DumpPpcRange.java` accepts
pairs of guest address and byte count, and prints raw big-endian words plus
disassembly. Inline pointer tables are data even when a word also decodes as
an instruction. Keep Ghidra projects and exported game bytes under `work/`.

See [the control-flow investigation](../docs/findings/2026-10-30-native-build-and-control-flow.md)
for the exact sites, table entries, and validation limits.

To audit the exact inline absolute-table idiom, run
`ghidra/ExportInlineSwitches.java` in a read-only Ghidra session, passing an
output TOML path such as `work/inline-switches.toml`. Then compare it from the
repository root:

```powershell
python tools/audit_inline_switches.py work/inline-switches.toml port/generated/default
```

The investigated image has 1,762 recognized tables; the final hints leave zero
truncated prefixes or target/selector disagreements. `--output NEW_FILE.toml`
can propose verified prefix extensions for review; it refuses to overwrite an
existing file. This does not audit other switch forms or arbitrary callbacks.

The final 2026-10-30 startup test stayed alive for 30 seconds after initialization,
then was deliberately stopped. On 2026-10-31, the user confirmed a successful
menu boot. A subsequent gameplay-start attempt crashed on missing callback
`8471B2F0`, then a retry reached the neighboring `8471B2E8`. The full 25-entry
thunk family has now been audited and its four missing entries registered.
The next attempt renders an arena introduction with visible geometry artifacts,
then stops at another missing callback, `848B6FA0`. Its 185-record table region
has now been audited and both missing entries registered.
At this earlier stage interactive gameplay was unverified. The later ROV
validation below establishes live gameplay rendering. Allocation errors and kernel/network
stubs remain in the earlier logs; their resolution has not been established.
See [the menu-boot finding](../docs/findings/2026-10-31-menu-boot.md).
See [the gameplay-crash finding](../docs/findings/2026-10-31-gameplay-startup-callback.md)
for the observed failure and correction.
The [arena-introduction finding](../docs/findings/2026-10-31-arena-intro-callbacks.md)
records the subsequent callback repair and the separate rendering symptoms.
The next attempt reached a different missing callback, `84AB8CA8`; its verified
global-load/tail-call wrapper is now registered. See the
[scripted-callback finding](../docs/findings/2026-10-31-scripted-gameplay-callback.md).
The following attempt reached `848E3A00`; its original flag-bit clearing body
is registered in the [flag-callback finding](../docs/findings/2026-10-31-gameplay-flag-callback.md).
The pre-run-out black flash prompted a packed-vector translation audit. The
type-6 pack/unpack correction now preserves the required biased float bits,
component order, source half, saturation and overflow behavior. Its numeric
tests match Xenia; visual confirmation is still required. Log 009's missing
`8471B108` callback and seven verified siblings are also registered. See the
[packed-vector finding](../docs/findings/2026-10-31-packed-vector-geometry.md).
The user subsequently confirms correct camera/replay rendering and supplies
a coherent paused scene, but live gameplay stays black. Log 010 closes normally.
Use `tools/launch_render_diagnostic.ps1 -Profile rov` for the first isolated
render-target comparison (`baseline` and `synchronous` are also available).
Run folders contain settings, runtime logs, and process CPU samples, not GPU
frame timings. ROV was subsequently user-validated to restore live gameplay
and is now the working launch setting; other profiles remain diagnostic. See the
[live-gameplay finding](../docs/findings/2026-10-31-live-gameplay-black-screen.md).

For slowdown investigation, the diagnostic launcher now captures GPU/host
presentation timings if the official portable PresentMon executable exists at
`work/tooling/presentmon/PresentMon-2.6.0-x64.exe`. Trace failures are logged;
ETW access may require an administrator shell. `-Profile rov-ui` compares UI-thread
presentation while retaining ROV; it is an unproven performance experiment.
Use `python tools/summarize_presentmon.py PATH/TO/presentmon.csv --start 30 --end 60`
to summarize one timeline window. Host presentation rate is not gameplay FPS.
See the [performance finding](../docs/findings/2026-10-31-performance-investigation.md).
The completed user test shows a 30.95-second pipeline-creation startup stall
and expensive later GPU work. Whole-run medians hide that cost; use bounded
timeline windows, p99 and long-record counts. No performance fix is verified.
Captures now have a default 600-second stop timer (`-CaptureSeconds` overrides
it), and `trace.json` records the exact session/PIDs for targeted cleanup.

Remote profiling can run without capture-key input. The diagnostic launcher
also writes `guest-frames.csv`; use `tools/summarize_guest_frames.py` with
`--start`/`--end` to inspect guest submission cadence. Optional timed RenderDoc
device captures and native replay/AMD telemetry tools are documented in the
[remote profiling finding](../docs/findings/2026-10-31-remote-renderer-profiling.md).
The later measurements refine the GPU attribution above: normal clocks and
substantial gaps outside summed draw costs point to CPU/synchronization work
still requiring investigation. There is no verified speed fix yet.

For a manually operated diagnostic run, use
`tools/capture_gpu_workload.ps1 -ShaderState optimized -ManualTrigger -GpuStats -DurationSeconds 600`.
Open the desired scene yourself, then create the empty `capture.trigger` file
inside the run directory printed by the script. This starts a five-second
native device capture across presentation boundaries; it sends no game input.
The script still stops at its deadline. Close the game before timing a replay
so the GPU is idle. `-DepthState baseline|optimized` selects the independently
controlled depth specialization in both capture and ordinary benchmark tools.

The [menu write/blend finding](../docs/findings/2026-11-01-menu-write-and-blend.md)
records an incremental 3% timed-menu GPU reduction for full writes and a 29.76%
reduction for the selected asymmetric overlay draw, with identical replay output.
These are GPU-cost measurements; the menu lag and black flashes are subsequently resolved in the user-tested native D3D12 configuration below; whole-game FPS remains unestablished.
Both benchmark/capture scripts accept `-FullWrite baseline|optimized` for controls.

Automatic D3D12 now uses native render targets with bounded ownership extents
and synchronous pipeline creation. The user validated responsive 2K Nav and
no black flashes in gameplay/replay/camera changes, including their normal
2560x1440 borderless launch. Persistent caching stays enabled. Accurate Xbox
blending retains the slower ROV compatibility fallback; Vulkan Automatic stays
FSI and its native FBO mode remains experimental. See the
[native pause-menu fix](../docs/findings/2026-11-01-native-pause-fix.md).
