# Modding the ZMO beta

This guide describes the folder-based Xbox mod system in `ZMO-beta1`.
The [editor export contract](formats/mod-folder-editor.md) specifies every manifest
field and payload layout. [CHMOD API 1.3](formats/chmod-1.3.md), the
[JSON schema](formats/chmod.schema.json) and the [native SDK](../sdk/README.md)
provide the validation and extension contracts. CHMOD remains the internal API
name. A mod can be distributed as an ordinary folder.

The [modding policy and development plan](MODDING_POLICY.md) defines package
distribution, the shared project DLL, authoring checks and release updates.
See the [recomp backlog](MODDING_BACKLOG.md) for planned features and ownership.

## Install and organize

Use **Install mod or collection** in Mods, or drag the folder into that window.
A package root contains `mod.json`. A collection groups independent packages:

```text
mods/
  College Hoops Reborn/
    Presentation Mods/
      Button Style/mod.json
      ESPN/mod.json
    Uniforms/
      Conference A/Team Uniforms/mod.json
    Courts/
      Conference A/Team Court/mod.json
    Rosters/Season Roster/mod.json
```

Each package has its own manifest and declared payloads. A collection has no
aggregate 512 MiB cap. Each child remains limited to 512 MiB, 4,096 asset entries
and 8,192 tree entries. A single manifest around an entire overhaul still has
those package limits. Recursive discovery stops at package roots and is bounded
to 8,192 visited folders. Folder rows enable or disable the newest version of each
child together. Child rows select versions and priority. Dependencies remain exact
ID/version pairs regardless of directory location.

Keep editor project files, source artwork and backups outside exported packages.
Every exported payload must be inventoried and hashed. Import and validation do
not execute DLLs. Native execution requires the launcher's explicit opt-in.

## Find the right asset

Use the pristine loose install as the source. `assets.json` identifies banks;
bank `asset.json` identifies records and decoded components. `scene_textures.json`
identifies embedded image slots and their exported DDS paths. Follow
`asset_path_aliases.json` for supported earlier names. See the
[loose asset format](formats/loose_assets.md).

SCNE textures live beside their owning data, for example
`assets/s272.iff/floor.scne/floor_diffuse_8fc00df1.dds`.
Recovered geometry, material and resource names help identify them. Hashes,
record indices and slot numbers remain authoritative when names are ambiguous.
Support maps can be required lighting, bump or reflection data. Their folder
classification does not make them disposable. Preserve unknown headers, palettes,
formats, stream declarations and ownership metadata.

DDS is the editable texture payload. A PNG or PSD working image must be encoded
for the target template before export. A filename alone does not establish format
compatibility. Embedded images retain validated dimensions, compression, face and
mip layout. Standalone replacements have a separate validated upscale policy.

## Choose the export type

| Task | Payload and capability |
| --- | --- |
| Replace an existing texture, including stock uniform artwork | `assets/` DDS, `dds.replace`, exact record and optional texture slot |
| Make a one-image court with original decorative lines hidden | Paired CPU/GPU floor components, `court.scene` |
| Shorten supported shorts | Matching render positions and simulation constraints, `cloth.positions` and `cloth.simulation` |
| Add alternate uniforms or replace a complete stock uniform bank | World/selection bank pairs under `uniforms/`, `uniform.register` |
| Supply an editable native roster | Xbox payload and aggregate header under `rosters/`, `roster.expose` |
| Change executable behavior through published hooks | Native DLL under `code/`, typed extension capabilities |

An asset entry binds the source bank hash, record index/ID/type, source digest,
target path, payload path and replacement digest. Embedded images also bind their
slot. Never guess these from the display name. Arbitrary DAT replacement, generic
scene topology changes, animation, LAYT and audio do not have a general export
capability. Viewing a resource in Studio does not imply a loader writer exists.

For a full court, use **Build Court.cmd** or the installed native tool:

```text
ch2k8_tools build-full-floor GAME s###/artwork.dds MODS
ch2k8_tools audit-full-floors GAME
```

Use the UGA artwork layout in a 2048 x 1024 BC1/DXT1 DDS with 12 mip levels.
The builder preserves the supported stock lighting geometry while hiding the
original decorative draws. Check the audit for supported layouts. Split or
unrecognized courts require additional conversion. Ordinary DDS repainting keeps
the original court geometry and markings.

Uniform letters `h/a/x/y/z` mean Home, Away and Alternates 1/2/3. Pair each world
bank with its `sel` selection bank. Artwork ID differs from team/roster owner ID.
New Home/Away routes require a matching packaged roster. Alternate pairs can
inherit uniquely resolved Home ownership and characteristics. Optional
`neck_shape` values 0 through 4 select U, V, V triangle, Triangle and Wishbone.
Stock bank replacements remain bound to their exact template and layout digest.
Number/name sheets retain validated palette and glyph metrics. Studio-generated
bump and green maps are authoring outputs and must pass the same template checks.

## Stage and launch

The launcher validates manifests, content hashes, source identities, dependencies,
conflicts and native permissions before preparing a private overlay cache. Vanilla
assets remain the source. Mods supply replacements through the overlay rather
than saving edits into that source. Staging publishes progress and reuses a matching
prepared cache. A changed selection or input invalidates the cache. This improves
repeat launches without promising a fixed preparation time for large overhauls.

Priority runs low to high. Ordinary DDS entries for the same target use last wins.
Whole-scene overlaps, scene/slot overlaps, conditional DDS conflicts, competing
rosters and exclusive uniform/hook claims reject. Apply changes through the
launcher and restart. Avoid editing generated caches by hand.

Selection state is in `port/userdata/mods.json`. Profiles and staging outputs are
separate under `port/userdata/`. Roster/code selections can choose isolated save
profiles, so a different selection can expose a different save set. Preserve the
active profile when testing a custom overlay. Export roster edits as a roster mod
or native save. Do not write those edits back into vanilla assets.

## Presentation extensions

The published Button Style hook combines a native choice provider with conditional
PlayStation DDS payloads. Coverage includes menu/controller prompts and the
supported on-court passing atlas. See [Button Style](../sdk/BUTTON_STYLE.md).

ESPN and USA Sports scorebugs use a separate opt-in [CHMOD ABI 2 preview DLL](../examples/scorebug_preview/README.md)
and converted Xbox scenes in an overlay. A style change takes effect when the
next match loads. The preview targets a matching executable and uses internal
hooks. Live rendering and menu behavior still need gameplay verification.
See [conversion and live-element research](findings/2026-11-19-scorebug-elements.md)
for tooling and native addresses.

Native mods currently target Windows x64. A DLL is executable code and is not
portable to macOS by copying it. See the [Mac portability assessment](research/mac-portability.md).

## Author and verify

Open a pristine install in Studio, select supported assets, and keep edits in a
mod project. Export a versioned folder with the exact inventory and hashes. Run
manifest resolution and the native validators listed in the editor contract.
Inspect a staged overlay before testing in game. Keep the runtime, tools and SDK
versions together. Record structural validation and gameplay verification
separately. [Recent research](research/zmo-beta-research.md) lists the current
scope and unresolved work.
