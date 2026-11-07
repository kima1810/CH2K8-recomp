# 2026-11-01: Native Vulkan backend and display launcher

## Question

Enable native Vulkan rendering for the Windows recompilation and provide a
basic launcher that selects resolution and refresh rate. Retain the working
D3D12 ROV path for comparison; remote testing must not require keyboard input.

## Method

Use the existing ReXGlue Xenos Vulkan command processor, SPIR-V translator,
render-target cache and native Vulkan presenter. Build the exact previously
used SDK revision, `bd833a2ab69d305f99ddf57418fc38ffec8af93d`, with both
`REXGLUE_USE_D3D12=ON` and `REXGLUE_USE_VULKAN=ON`. The official Windows
binary SDK was D3D12-only. A separate source checkout, SDK prefix and game
preset keep this build isolated:

- Source: `work/third_party/rexglue-vulkan/`
- SDK: `port/sdk-vulkan/`
- Game preset: `win-amd64-vulkan`

`tools/build_vulkan_sdk.ps1` fetches the pinned dependencies, prepares the
source, builds/installs Release, then builds the game. Pinned Vulkan-Headers,
VulkanMemoryAllocator, SPIRV-Tools and glslang supply development dependencies;
the installed graphics driver supplies the Vulkan implementation. No full
LunarG installer or driver replacement is required for this build.

The application selects `ch2k8_renderer=d3d12|vulkan` in `OnPreSetup` through
the GPU plugin's existing backend factory. Failed explicit selection stops
with an error instead of falling back to another API. The normal default is
D3D12; the new build contains both backends. The opt-in RenderDoc capture
worker now accepts the Vulkan provider's instance dispatch handle as well as
the D3D12 device.

For capture-independent remote validation, `ch2k8_output_capture=PREFIX` uses
the presenter's thread-safe `CaptureGuestOutput` API and writes numbered BMP
files. Delay, count (bounded to ten) and interval are optional flags. The
worker is joined before presenter teardown and is inactive by default.
This reads the game's native framebuffer rather than the desktop.

## Build blockers addressed

**[CONFIRMED]** Windows Git checked libmspack's tracked file symlinks out as
text placeholders. Its C files then failed compilation on their first line.
The preparation tool materializes those links from Git's recorded targets,
requiring targets to remain inside that dependency. No global Git or Windows
developer-mode setting is changed.

**[CONFIRMED]** The pinned SDL window implementation requests exclusive modes
with `refresh_rate=0.0`, ignoring the configured refresh rate. The preparation
tool replaces that single call argument with `video_mode_refresh_rate`.
SDL still selects the closest supported hardware mode and logs the actual
resolution/Hz. This does not guarantee arbitrary requested rates are supported.
The preparation tool refuses another SDK revision or an unfamiliar selector.

The SDK also omits the RenderDoc application header required by its public
Vulkan provider headers. The game includes its existing licensed header
directory when compiling the capture integration.

## Launcher behavior

`Launch CH2K8.cmd` opens `tools/launch_ch2k8.ps1`. The small Windows Forms UI
offers renderer, five resolution presets from 720p to 4K, refresh rate from
24–240 Hz, and windowed/borderless/exclusive modes. It validates the extracted
disc's `default.xex` and the selected build before launching. Successful
launches save choices to ignored `port/userdata/launcher.json`.

The dual-backend executable is preferred for both choices when available.
D3D12 requests ROV; Vulkan leaves render-target selection to the runtime's
capability checks. Resolution configures the guest video mode and startup
window; it is not a universal internal render-resolution override. Refresh
configures guest timing and, in the patched exclusive-mode build, requests
the closest display mode. Borderless follows the desktop display mode.
60 Hz retains the original guest timing.

`-ValidateOnly` emits the actual configuration without launching or saving;
`-Launch` provides the same choices without UI for remote tests. Preview
rendering verifies the launcher layout without starting the game. The
diagnostic launcher adds `vulkan` and `vulkan-fsi` profiles; FSI is an optional
correctness experiment requiring supported fragment shader interlock.

## Evidence and validation

The separate dual-backend SDK builds and installs successfully. The launcher
was rendered and visually inspected. Three argument-building tests cover
renderer selection, display modes, refresh/resolution forwarding, paths with
spaces and missing-disc rejection. Both Release game builds pass; the full
repository suite is **41 passed, 1 skipped**. A numeric BMP test verifies row
stride, top-down orientation and RGB channel preservation.

**[CONFIRMED]** Native startup selects the AMD Radeon RX 6650 XT with Vulkan
device API 1.4.315 and creates graphics pipelines. A 60–110 second autonomous
run records a median 74.666 ms guest submission interval (13.39 submissions/s).
Its scene state and output settings differ from the earlier ROV runs, so this
does not establish a speedup. Slow gameplay remains unresolved.

The capture-independent Vulkan run `20261101-003007-134-vulkan-readback`
produces a black image at about 60 seconds, followed by a coherent 1280×720
USC Upstate arena with players, crowd and court at about 120 seconds. The
second image shows demo-mode warmups and a 5:00 clock. This confirms native
Vulkan scene rendering, but does not prove that the previously failing live
exhibition phase or a complete match has been validated. The first black
sample alone must not be treated as a persistent renderer failure.

Physical exclusive display-mode switching is not exercised during the remote
test; forwarding and nearest-mode selection are verified in source and tests.

The FSI comparison (`20261101-003231-856-vulkan-fsi-readback`) also captures a
coherent Army arena, players and crowd at about 120 seconds after a visible
loading screen at about 60 seconds. During seconds 70–110 its median guest
submission interval is 75.478 ms, compared with 81.534 ms in the default-path
readback run. Different teams, scene states, pipeline compilation and readback
perturbation prevent treating this as a controlled speed comparison. Neither
path demonstrates a verified speed fix. Automatic capability selection remains
the launcher's Vulkan default; FSI stays an explicit diagnostic profile.

The Vulkan preset additionally requires `REX_HAS_VULKAN=1` from the SDK's
exported runtime target. Positive configuration passes, while deliberately
configuring against the original D3D12-only SDK fails with an actionable error.
This prevents CMake's package search from silently producing a mislabeled build.

RenderDoc 1.47 DLL injection alone does not activate its Vulkan layer on this
machine; the timed capture reports a failed start. A second attempt enabling
the layer only through child-process environment variables fails Vulkan
instance creation with `ErrorExtensionNotPresent`. The uninstrumented Vulkan
backend initializes successfully. No global layer registration is performed;
the built-in readback API provides the alternative validation path.

## Conclusion and open questions

The [native-state follow-up](2026-11-01-native-constant-state.md) adds native
constant caching and bulk packet decoding. Subsequent black FBO captures
reproduce with those features disabled, so Automatic Vulkan now requests FSI
and native render targets remain an explicitly experimental launcher choice.

The [later GPU-backend investigation](2026-11-01-gpu-backend-investigation.md)
extends Vulkan FBO and FSI validation to live demo gameplay, with visible HUDs
and advancing clocks after the CPU optimizations. It also compares the native
D3D12 paths. Full exhibition completion and Legacy/save behavior remain open;
API selection alone still has no verified large performance gain.

Vulkan uses native host Vulkan through the existing Xenos-to-SPIR-V runtime.
Rendering correctness, performance, full-game completion and Legacy/save
behavior require runtime evidence; no speedup is implied by changing APIs.
Raw builds, extracted assets, captures and logs remain local and ignored.
