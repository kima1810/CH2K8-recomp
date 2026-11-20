# CHMOD schema 1 / mod API 1.3.0

For the current folder-first layout, editor export rules, and current runtime
variants, see the [mod folder editor contract](mod-folder-editor.md). The
original API 1.3 court and extension notes follow.

## Court SCNE assets

`court.scene` is a schema 1 asset capability for the source-verified Xbox
Georgia floor layout. Include two `assets` entries with this kind and the same
bank hash, record index, record ID and SCNE type. Component 0 targets the
CPU `block0.dat` and component 1 targets the GPU `block1.dat`. Each entry
binds the original component SHA-256 and packaged payload SHA-256. Include
`court.scene` in `capabilities` and require mod API 1.3.0.

The launcher requires both components, verifies exclusive ownership, and
validates them together before staging either. Both files retain their original
size. Packages can edit the existing floor's float3 positions and packed UVs.
The full-floor conversion also allows a specific texture descriptor update,
suppression of the paint, center-logo and lines draw runs, and 2048×1024 tiled
BC1 artwork in the disabled center-logo allocation. Index buffers, vertex
counts, material/shader structure, and other bytes are preserved.

This capability requires a launcher and `ch2k8_tools.exe` with the
`validate-court` command. The current implementation recognizes one original
CPU/GPU hash pair. New court layouts and other SCNE types require their own
verified contracts. `cloth.positions` remains the format for the three
converted shorts variants. See the
[court integration evidence](../findings/2026-11-12-chmod-court-scene.md).

API 1.3 retains [1.2 data contracts](chmod-1.2.md) and ABI 1 packages and adds the
Studio-hosted [public extension SDK](../../sdk/README.md). There remain three
content classes: assets, native roster/save data and native code. No new Legacy
resource or JSON gameplay-patch format is introduced.

An ABI 2 extension entry has exactly `file`, `sha256`, `abi: 2`, `capabilities`
(required nonempty supported string array) and `replacements` (possibly empty).
The package also declares those capabilities plus its data capabilities in the
existing top-level exact union. `requires.mod_api` must be `1.3.0`. Existing ABI 1
entry shape remains `{file,sha256,abi:1,hook:"player.weight.read"}`. One DLL per
package, up to64 selected modules. ZIP/unpacked security and explicit native opt-in
remain unchanged; no DLL executes during installation/metadata inspection.

Capabilities: `hook.player.weight.read`, `hook.player.weight.write`,
`lifecycle.runtime.ready`, `lifecycle.runtime.stopping`, `data.player.weight.read`,
`data.player.weight.pending_write`. Available hooks, signatures and evidence are
in [hook_registry.json](hook_registry.json). Unresearched domains are explicitly
unavailable. Replacement claims list semantic hook names (`player.weight.read` or
`player.weight.write`) and require their hook capability. Two exclusive claims
conflict before launch. Observers/transformers compose. ABI 1 weight-read remains
exclusive with ABI 2 weight-read selections to preserve the prior contract.

Exact dependencies order native module initialization topologically, then stable
user priority. Within each phase: module order, local registration order value,
registration sequence. Package dependency cycles/incompatibilities still reject.
Runtime registration enforces capabilities, versions, phases and replacement
exclusivity independently of launcher preflight. Initialization failure rejects
loading as a whole; prior module registrations retire and shutdown runs in reverse.
Native module process side effects cannot be rolled back or sandboxed.

The executable-adjacent capability receipt now advertises API1.3, ABI1/2, hook
names, required capabilities and exact exe/XEX digests. Newer ABI2 modules reject
older receipts actionably; ABI1 accepts compatible1.2 or1.3 receipts. Receipt
creation requires linker-map evidence for both researched wrappers and originals.
Native config is1.3 when ABI2 is selected and remains1.2 for legacy-only selections.
Existing isolated profiles, native-code update escalation rules, and recovery
`CH2K8_MODS_DISABLED=1` are preserved. No hot unload exists.

See SDK [contracts](../../sdk/CONTRACTS.md), [authoring](../../sdk/AUTHORING.md),
[adding hooks](../../sdk/ADDING_HOOKS.md), [acceptance](../../sdk/ACCEPTANCE.md), and
[research/compilation report](../findings/2026-11-08-extension-framework.md).
All current ABI2 game semantics remain Researched/compiled, not in-game verified.

## Capability addition: native Presentation Button Style

`hook.presentation.button_style` adds typed semantic hook 5 without changing the
ABI 2 host layout. Paired DDS entries may declare `selection` equal to
`presentation.playstation`; both researched global.iff atlas identities and one
provider must be in one package. Overlapping overrides reject. Exact hashes,
source identities, native opt-in and isolated profiles still apply. Matching
runtime/GPU capability evidence is required. See [contract](../../sdk/BUTTON_STYLE.md).
The added capability gates compatibility with older API1.3 runtimes.
