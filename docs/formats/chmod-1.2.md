Retained API1.2 data contracts; see [current API1.3 extension additions](chmod-1.3.md).

# CHMOD schema 1 / mod API 1.2.0

This is the current specification. [API 1.1](chmod-1.1.md) defines retained DDS,
cloth, native roster, package security, priority and update contracts. Its rejection
of executable content and new uniform banks applies only to the older profile.
[The exact JSON schema](chmod.schema.json) and launcher semantic validation are
both required. No arbitrary binary edit language is provided.

API 1.2 uses the same supported XEX and recomp revision as API 1.1. Packages may
combine all three content classes atomically. Declare `requires.mod_api: "1.2.0"`
for `uniforms` or `extensions`. Metadata, dependencies and every payload SHA256
remain mandatory. Enabled state and order remain outside the package.

## Additional uniforms

Optional `uniforms` is an array of 2..64 bank entries. Alternate-only packages
may omit `roster`; the launcher derives native roster links automatically as
described below. New Home/Away banks still require a same-package native roster.
Declare content `assets` and capability `uniform.register`:

```json
{"name":"uh0999.iff","template_hash":123,"template_layout_sha256":"<64 lowercase hex>",
 "folder":"uniforms/uh0999.iff","files":[{"path":"asset.json","sha256":"<64 lowercase hex>"}]}
```

This illustrates field shape only: template 123 and art ID 999 are NOT verified
or reserved identities. Export actual identities and full required inventory from
the user's Xbox installation. Existing bank structures are reused, not a new model
format. Each inventory path is relative to this entry's `folder`, not the package
root. The example omits the other required files for brevity; a one-file inventory
rejects. Include every required component and
DDS, with hashes. The native validator derives a sanitized layout rather than
trusting authored metadata. World/selection source categories must match.

Names are `(sel)?u[haxyz][0-9]{3,4}.iff`, canonical art IDs 0..1023 with at least
three digits. Name-derived uppercase ASCII CRC identifies a bank; occupied IDs,
shared component hazards and collisions reject. Each art/variant needs both world
and selection banks. Existing explicit package roster routes must have an owner
assigned to a native team; missing alternate routes are derived at launch.
Original source template layout SHA256 and all immutable
component bytes must match. Only recognized BC texture payload spans may change;
record structure, bounds, padding, CPU/GPU sizes and nontexture bytes remain fixed.
World templates need existing uniform and shorts records. Texture identities must
be private relative to known source catalog and other new banks. Standard native
DDS format/mip/upscale restrictions remain. Existing `assets` entries cannot target
these added banks. This supports template-compatible uniforms, not arbitrary meshes.

### Automatic alternate activation across native rosters

The launcher detects active, validated uniform-folder pairs from `uniforms` entries:
`ux###.iff`/`selux###.iff`, `uy###.iff`/`seluy###.iff`, and
`uz###.iff`/`seluz###.iff` (Alternate 1/2/3). Case and canonical naming follow the
manifest rules. Folders must still have source-bound component metadata and full
integrity inventory; stray undeclared directories do not bypass package validation.

The artwork number is NOT a team index or uniform owner. In each roster, the
loader finds the unique assigned owner whose Home/Away route uses that artwork
ID, or an existing explicit alternate route to the same ID. It adds a missing
alternate by copying that owner's Home row, retaining unknown fields/shape,
setting the requested artwork/variant and clearing the known seven-bit unlock
field, matching Studio's Xbox append operation. Existing routes to the same art
are unlocked; a slot assigned to different art rejects. Missing/ambiguous owners,
missing Home templates, editor dormant-row metadata and limits reject the whole
activation rather than guessing which team should receive artwork.

All supported native roster packages under each XUID in the current baseline
Dummy HDD and selected isolated profile are considered:
`<XUID>/54540818/00000001/<name>.ROS/<name>.ROS`, with the existing parallel
`Headers/00000001/<name>.ROS.header`. SDK headers must match the package filename,
title, content type and neutral/storage XUID; roster body/wrapper and relationships
must validate. Named saves retain their actual names and headers. ASCII names with
spaces are supported; unsupported names/case/wrappers stop activation. No roster
is invented if none exists. Inactive isolated profiles are processed when selected,
not rewritten globally. Legacy files and other save types are never touched.

Before launching, all target changes are staged and originals backed up under
`port/userdata/uniform-activation/`. A durable journal precedes per-file atomic
replacement. Crash recovery/next launch, disabling or launch without mods restores
unchanged managed files first, then applies the selected set. This is a journaled
multi-file transaction, not filesystem-wide atomicity. Original wrappers are
updated for appended table size; existing body bytes other than the uniform-table
descriptor remain unchanged. Headers are not rewritten.

If a roster or header has changed since activation, automatic switching stops
without overwriting that save. Preserve it and its activation backup before manual
reconciliation. This conservative limit also applies to game-saved edits; semantic
merging of independently edited saves is not implemented. Backups and completed
journals are retained. Activation is capped at 256 files/1 GiB. The operation occurs
at launch, never while the game is running, and currently remains untested.

## Executable extension

Optional `extensions` contains exactly one entry. Declare content `code` and
capability `hook.player.weight.read`:

```json
{"file":"code/weight_read.dll","sha256":"<64 lowercase hex>","abi":1,"hook":"player.weight.read"}
```

Only Windows x64 PE DLL, ABI 1 and this named hook are accepted. One exclusive
registration across selected mods; priority does not override exclusivity.
Use [the C ABI header](../../port/src/mod_extension_abi.h), exporting
`ChmodQueryExtension`. Descriptor is 24 bytes; borrowed call context is 16 bytes.
No C++ objects or guest pointers cross the ABI. The guest anchor is an opaque
32-bit guest address, never a host pointer. Callback is synchronous, thread-safe,
nonthrowing and valid through process exit. No hot unloading. Return 100..400
pounds; other returns and caught C++ exceptions preserve the original result.

`player.weight.read` wraps the researched guest getter `84752968`, calls the
original first and exposes its return. It does not intercept direct field reads
or prove physics, simulation or Legacy behavior. Guest code may persist derived
results. Native-code selections therefore use isolated persistent Dummy HDD
profiles with no existing Legacy saves copied. This is not an OS sandbox.

User opt-in to unsandboxed DLL execution is required in Mods and defaults off.
The runtime verifies the launch config, XEX compatibility, file hash and ABI before
loading. The launcher requires adjacent `chmod-runtime.json`, bound to executable
SHA256 and supported hook names. Build tooling creates it from linker-map evidence.
The package cannot select arbitrary guest or host addresses. Additional hook points
require researched runtime/codegen work and recomp distribution first. Ordinary
mods using this supported point need no recompilation.

DLLs execute with the user's full access and may crash or change files. They are
never loaded during package metadata inspection. Updating a data-only package to
code requires manual review/install/enable rather than silent escalation. Recovery
launch sets `CH2K8_MODS_DISABLED=1`, ignoring native mod dispatch even if cvars persist.

## Status

Implemented and compiled, **Researched**, current isolated and gameplay verification
pending. No game was opened and no acceptance tests were run for API 1.2. See
[evidence](../findings/2026-11-08-chmod-api12.md) and
[user acceptance](../CHMOD_ACCEPTANCE.md). Existing Legacy saves are never migrated.

### Vanilla jersey availability and fallback

On normal launcher starts, existing native uniform routes have their known
seven-bit unlock field cleared for every Home/Away/Alternate slot, independently
of folders inside mods. Additional vanilla alternates are discovered by exact
name CRC in the original Xbox catalog: a world and selection identity must both
exist. Missing native alternate routes are added using the same unique artwork
owner/Home-template rules. Catalog candidates unused by a roster or lacking a unique owner are skipped;
an occupied different-art alternate remains intact and is unlocked. Mod-added
alternates override the same artwork/variant request and require a resolvable owner.

Prepared mod caches retain baseline resources; an absent replacement therefore
uses the original game's resource. The presence of a mod folder is not required
to unlock an existing base-game jersey. A complete native jersey that the original
catalog cannot identify is not fabricated. No arbitrary missing bank is silently
substituted with a differently identified jersey.

`Launch without mods` is the recovery exception: it restores unchanged journaled
rosters and skips both automatic linking and vanilla unlocks, retaining a true
baseline launch. Disabling a mod followed by normal launch removes its additions
and reapplies vanilla unlocks. No tests or actual-save activation were performed
by the agent for this follow-up.
