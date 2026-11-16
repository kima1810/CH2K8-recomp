# Presentation button-style extension research

Status: **Researched**, implemented and compiled; not in-game verified. No game was
launched, tests executed, or user saves modified during this investigation.

Supported input: Xbox 360 XEX SHA256
`71e8983d1cc009e485696aad19b5fa4b4661761870e2c8972717b932c1e4be36`.
Evidence comes from the generated PPC function bodies and read-only Ghidra
inspection of that image. This is Xbox evidence, not a PS3 menu layout.

## Native Presentation menu

The UTF-16 identifier `OptionsMenu_PresentationMenu` starts at `0x846d9158`.
Its definition is at `0x8214c288`: name pointer at +4, event map at +8,
default event handler at +12, row-table pointer at +28, row count at +64.
The stock row table is `0x85548a28`, with 24 rows of 92 bytes.
`sub_847D9E50` computes a row pointer; `sub_847D9E60` computes its work area
at row +76. These are runtime internals, not proposed public SDK layouts.

`sub_847DC530` handles native menu events. Event 3 constructs the menu through
`sub_847DB940`, `sub_847E0668`, and `sub_847DBAF8`. `sub_847E0668` iterates
the definition's row count and initializes row work state. `sub_847E09A0`
builds the row UI. `sub_847E2200` and `sub_847E2308` invoke the selected
row's handlers. `sub_847E2C10` resolves the controller's current definition.
Static evidence supports investigating an appended native boolean-style row;
it does not prove scrolling, layout, focus, or persistence in a running game.

The first stock row is type 5. Its label expression cell is at descriptor +4;
callbacks occupy +12 through +36, including handlers at +24/+28 and value
text/width providers at +32/+36. Its final 16 bytes are mutable work state.
Any future adapter must preserve original rows and initialize new work state,
rather than copy live UI ownership into a second row.

Native strings are tagged expressions, not UTF-16 label pointers. Odd values
are tagged identifiers; even nonzero values refer to managed expressions.
`sub_84863460` copies an expression with reference handling;
`sub_848645A0` increments expression references; `sub_848646C8` releases them.
`sub_848635D8` calls `sub_84864758`, whose type-4 expression retains a UTF-16
source pointer and length; `sub_84D5A028` counts 16-bit code units to NUL.
The literal constructor is now used with process-lifetime source storage.
`sub_84863540` composes expressions/format arguments and is not used as a raw
UTF-16 constructor. Invented localization hashes are unsuitable.

ReXGlue's `FunctionDispatcher::AllocateThunk` provides runtime callback
addresses within the module's thunk reserve. New handlers must use this
facility, not fabricated guest addresses or host pointers cast to PPC addresses.
Any interception must preserve both generated direct calls and indirect dispatch.

## SDK and package requirements

The requested location is the **original game Options → Presentation menu**.
The extension must ship as a normal `.chmod` package with declared, checked
capabilities and hashes for its native DLL and supplied artwork. It must not
edit the installation or user saves. Original Xbox textures are the fallback.
The two supplied PS3 JPEG atlases lack alpha and differ in resolution for the
stick atlas; conversion and transparent edges require explicit validation.
The separate navigation atlas has no supplied equivalent; coverage must be
reported honestly. Resource identities are recorded in the sibling
[Xbox button texture findings](2026-11-08-xbox-button-textures.md).

A semantic SDK service must own native row installation, callbacks, lifetime,
and render-thread texture switching. Public mod code should receive a typed
choice API and variant-selection API, not guest memory/register access.
The 80-byte `ChmodHostV2` ABI is unchanged. Existing typed dispatch now exposes
capability `hook.presentation.button_style` and typed ButtonStyle arguments/result.
The runtime owns native row and texture selection behavior. ABI 1/2 remain valid;
this is a narrow choice contract, not an arbitrary menu-construction API.

Texture switching must invalidate resident GPU textures and retire resources
using submission fences; changing a DDS filename alone does not update cached
textures. D3D12 source paths include `native_dds_d3d12.inl` and the SDK texture
cache. Vulkan support requires its own verified switching path. Missing backend
support must reject the capability rather than silently claim a working toggle.

Acceptance remains remote: native menu entry/focus/navigation, both complete
atlas selections, live cache refresh, baseline restore on disable/recovery,
re-entry/session lifetime, conflicting packages, unsupported runtimes/backends,
and unchanged user saves. Compilation must be reported separately from these
unexecuted checks. A compiled `.chmod` package is installed, disabled pending
explicit native-code opt-in and user selection. Runtime, GPU adapter, mod DLL
and synthetic dispatch test executable compiled. Installation inspected metadata,
hashes and PE structure without loading the DLL. No tests were executed.

Implementation: `port/src/mod_presentation.cpp`, SDK consumer
`sdk/examples/button-style/extension.cpp`, `tools/chmod.ps1`, conditional catalog
in `port/src/native_dds.h`, and reproducible `tools/prepare_native_assets_sdk.py`.
Root runtime binaries and receipt were updated after compilation; the prior
binaries remain privately available for rollback. Contract and limitations:
[SDK Button Style](../../sdk/BUTTON_STYLE.md).
