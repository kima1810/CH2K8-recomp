# Native Presentation Button Style hook

This is an implemented Xbox menu adapter and an actual SDK mod consumer, with
runtime acceptance pending. It is **Researched**, not In-game verified. Source
and binary compilation are distinct from the remote checks below.

## Contract v1

Capability `hook.presentation.button_style`, hook number `CHMOD_HOOK_BUTTON_STYLE`
(5), ABI 2, mod API 1.3. The 80-byte host ABI and existing hooks are unchanged.
An older runtime rejects this new capability; existing ABI 1/2 mods need no rebuild.

`ChmodButtonStyleArgs { action, current_style }` is immutable. `action` is QUERY
(0) after host publication and on native row installation or TOGGLE (1) on either native row direction/accept
handler. `current_style` is the host's current selection (0 Xbox, 1 PlayStation).
`ChmodButtonStyleResult { style }` starts at Xbox (0). A registered AFTER
TRANSFORM callback may return 0 or 1. BEFORE/AFTER observers are supported.
Argument transforms, cancellation, replacements and original invocation are
unavailable on this semantic hook. Unknown fields/values, callback exceptions or
failure statuses retire the failing registration and restore its incoming result.
With no successful transformer, the result remains Xbox.

The example in `examples/button-style/extension.cpp` preserves QUERY's current
selection and flips it for TOGGLE. It uses only SDK types, capability negotiation,
registration and logging. It has no guest addresses, offsets, raw memory access,
game imports, or GPU calls. It is an actual mod, distinct from the synthetic
weight examples. The runtime supplies the fixed label **Button Style**, choices
**Xbox / PlayStation**, and native row insertion in **Options → Presentation**.
This adapter does not expose arbitrary menu creation.

QUERY also executes on the host setup thread before guest launch, restoring the
last preference before texture use. Menu callbacks execute synchronously on the
native guest menu caller, serialized by the adapter. Values are borrowed for that callback only. Do not retain payload
pointers, enter guest/UI code, block, perform asynchronous callbacks, throw across
the ABI, or invoke shutdown. Framework ordering and lifetime rules apply. Only one
package may provide this capability; its observers may use local order values.
There is no hot unloading. DLLs remain unsandboxed, and native faults are not
contained by C++ exception handling.

Selection is persisted atomically in `chmod-button-style.json` beneath the
launcher's isolated native-mod user-data root. The file is a mod preference,
not a game save. No native settings structure, roster, or Legacy file is patched.
Fresh profiles start at Xbox. Re-entering the menu retains the active selection.

## Conditional assets

Each paired DDS entry adds `"selection": "presentation.playstation"` to the
existing source-bound asset contract. Both must be in the same package as the
provider. Only the researched `global.iff` TXTRs 270/`7542283f` and
410/`acc6d118`, bank hash 3680386632, are accepted. Original source SHA256,
record owner, DDS format/dimensions and shared pixel identities still validate.
Both payload hashes and the DLL hash are required. Conditional entries conflict
with any other override of those resources; priority cannot silently break the pair.

Preparation copies replacements into a private mod cache and writes
`native_dds_choices.index` after successful native asset preparation. The GPU
thread selects the conditional DDS only for PlayStation. For Xbox it uploads
the original guest texture. No retail fallback artwork is bundled in the mod.
Changing selection invalidates candidate textures, resets their watched ranges,
and reuses normal upload plus submission-fenced resource/descriptor retirement.
No GPU object is accessed by the DLL or guest menu callback.

This version requires **D3D12**, native DDS enabled, and matching runtime/GPU
binaries. The launcher checks the capability receipt's EXE and DLL hashes; the
runtime also checks the loaded GPU adapter's version. Vulkan is unsupported.
Recovery/disable removes the new row and conditional catalog on the next launch.

## Build and package

Build `chmod_button_style` from the SDK CMake project in an x64 developer shell.
The ordinary player installs the resulting `.chmod`; Python/build tools are
authoring requirements only. The separate `package_button_style.py` tool accepts
the user's 256x256 primary and 128x128 stick JPEGs plus the compiled DLL. It
reconstructs transparent backgrounds, upscales sticks to the Xbox 512x512 layout,
and writes BC3/DXT5 DDS payloads with their exact resource identities and hashes.

```powershell
cmake --build C:/dev/chmod-sdk --config Release --target chmod_button_style
python sdk/package_button_style.py --buttons primary.jpg --sticks sticks.jpg --dll C:/dev/chmod-sdk/Release/chmod_button_style.dll --output C:/dev/Button-Style.chmod
```

Pillow with DXT5 DDS encoding is required for this conversion. JPEG input has no
authentic alpha; reconstructed edges are a known quality limitation. The separate
navigation atlas (`d948c961`) and controller illustration remain Xbox, because no
matching replacement was supplied. This is not a claim that every UI prompt has
been converted or that PS3 input mappings are used. Input controls remain unchanged.
Artwork stays private and is not part of the public SDK repository.

Changing the artwork or choice logic within this contract needs only a new
`.chmod`, with updated version/hashes. Adding a third style, arbitrary labels,
another native submenu, additional resource identities, or Vulkan switching needs
new research/runtime adapters and a prebuilt recomp update. SDK headers alone
cannot add execution paths to an already installed runtime.

## Evidence and reproducibility

USA Xbox XEX SHA256
`71e8983d1cc009e485696aad19b5fa4b4661761870e2c8972717b932c1e4be36` only.
Generated `sub_847DC530` is strongly wrapped; `__imp__sub_847DC530` stays original.
Both generated direct native calls and the guest function map resolve the wrapper.
Native descriptors are researched from `sub_847D9E50`, `sub_847D9E60`,
`sub_847E0668`, `sub_847E09A0`, `sub_847E2200`, and `sub_847E2308`.
String construction follows `sub_848635D8` → `sub_84864758` → UTF-16 length
`sub_84D5A028`, with host-owned guest storage rooted until process exit.
Callbacks use ReXGlue `AllocateThunk`, never fabricated PPC/native addresses.
Menu identity, count, source table and callback signatures are checked before
publication; rejection retains the stock menu and logs a diagnostic.

Source changes live outside generated code. SDK renderer patches are reproducible
through `tools/prepare_native_assets_sdk.py` in the recomp. The compiled map and
capability receipt cover the wrapper and original. Static evidence is in the
recomp's `docs/findings/2026-11-08-presentation-button-style.md`.

## Remote acceptance — not executed

1. Enable the installed package and explicit native-code opt-in, choose D3D12.
   Confirm launch preparation rejects missing/changed atlases, DLLs or runtime.
2. Open original Options → Presentation. Find the appended Button Style row;
   verify all existing rows, scrolling, focus, help/footer and back navigation.
3. Toggle with left/right and accept. Confirm Xbox/PlayStation value updates and
   primary/stick graphics refresh live, including already resident textures.
4. Toggle repeatedly during menu navigation; observe no stale descriptors,
   corrupted sprites, device removal, leaked resources or delayed upload glitches.
5. Leave/re-enter; restart with the same isolated profile. Confirm selection
   retention. Invalid preference data should fall back to Xbox with a diagnostic.
6. Disable the package or Launch without mods; confirm vanilla row count and
   artwork. Original installation files and user saves must remain unchanged.
7. Check missing capability, old/mixed runtime binaries, Vulkan, two providers,
   an overlapping ordinary DDS mod, modified payloads, and recovery after failure.
8. Run prepared synthetic dispatch and package tests separately. These do not
   establish native menu correctness or replace the in-game checks above.
