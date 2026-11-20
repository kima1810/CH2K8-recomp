# Mac portability assessment

Status as of 2026-11-20: this checkout targets Windows x64. No macOS build or
hardware test has established support. Vulkan is useful for portability, but a
renderer backend alone does not port the launcher, runtime or native extensions.

## Reusable contracts

Loose assets, DDS containers, manifest identities, collection organization,
roster formats and guest hook research can carry across host platforms for the
same pinned Xbox executable. Guest addresses remain revision-specific. Native
extension binaries must be rebuilt for the host architecture and operating system.

## Required work

| Area | Current dependency and port work |
| --- | --- |
| Build/runtime | `port/CMakeLists.txt` includes mod extensions/presentation on Windows. Audit the pinned ReXGlue SDK, generated CPU code, memory/fault handling, windowing, audio and controller paths on Apple Silicon. |
| Native modules | `mod_extensions.cpp` uses Windows loading, PE validation, filesystem attributes, BCrypt and x86 intrinsics. Introduce platform adapters for library loading, binary validation, hashes, filesystem safety and floating-point state. |
| SDK | SDK CMake currently restricts builds to Windows 64-bit. Preserve the C ABI and ownership rules, add export visibility and explicit supported host architectures. |
| Presentation | The scorebug preview uses Windows DLL loading and atomic preference-file operations. Port these separately from the public hook API. |
| Packaging | `tools/chmod.ps1` accepts Windows DLL extension paths and checks Windows runtime receipts. Define platform/architecture variants before accepting dylibs or shared objects. |
| Studio/launcher | Studio invokes PowerShell and `ch2k8_tools.exe`. Provide a portable staging CLI/service and native tools, with equivalent validation and cache semantics. |
| Rendering | Validate Vulkan requirements through MoltenVK, portability enumeration, shader behavior, compressed texture support/fallbacks, alpha, reflections and synchronization. |
| Distribution | Sign/notarize the app and establish a deliberate policy for third-party native libraries under hardened runtime. |

Upstream [ReXGlue CMake](https://github.com/rexglue/rexglue-sdk/blob/main/CMakeLists.txt)
and [presets](https://github.com/rexglue/rexglue-sdk/blob/main/CMakePresets.json)
include macOS targets. This does not verify this project's pinned SDK and game.
[MoltenVK](https://github.com/KhronosGroup/MoltenVK) implements Vulkan over Metal
with portability requirements. See [Vulkan portability](https://www.vulkan.org/porting).
Apple documents [library validation](https://developer.apple.com/documentation/bundleresources/entitlements/com.apple.security.cs.disable-library-validation)
and [hardened runtime](https://developer.apple.com/documentation/xcode/configuring-the-hardened-runtime).
Entitlements should follow actual implementation needs.

Validate vanilla gameplay, saves, controllers and graphics on Apple Silicon first;
then texture/roster overlays; then a minimal native extension; then presentation
hooks and Studio. Rendering correctness and performance remain major unknowns.
