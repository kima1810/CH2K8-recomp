# Recomp mod folders and editor export contract

This is the folder-first authoring specification for the Xbox 360 ZMO-beta1
recomp. The package schema is version **1** and the current mod API is **1.3.0**.
Use [the schema](chmod.schema.json) for structural checks and the
[launcher](../../tools/chmod.ps1) and [native tools](../../tools/ch2k8_tools.cpp)
for semantic validation. Runtime support can vary between builds carrying the
same API number, particularly for full courts and Button Style.

## Folder layout

```text
ExampleMod/
  mod.json
  assets/                         # existing game resources replaced by this mod
    s272.iff/
      floor.scne/
        scene.dat
        scene_gpu.dat
  uniforms/                       # template-bound *new* uniform banks
    ux123.iff/
      asset.json
      ... declared component files and DDS ...
    selux123.iff/
      asset.json
      ... declared component files and DDS ...
  rosters/
    Roster.ROS
    Roster.ROS.header
  code/
    example.dll
```

Include only directories needed by the selected features. The example shows how
features can coexist; none of those payloads are mandatory for a texture-only
mod. Every file other than `mod.json` must appear in a manifest inventory. Keep
editor projects, source PSDs, OBJ files, previews, backups and private metadata
outside the exported folder. Store user enablement and priority in the
launcher, separately from package metadata.

Import the folder containing `mod.json`, or use either supported discovery
layout under `mods/`: a direct child with `mod.json` or a direct child containing
version folders with `mod.json`. Standard installed layouts are
`mods/<id>/mod.json`, `mods/<id>-<version>/mod.json`, and
`mods/<id>/<version>/mod.json`. The manifest ID and version are authoritative.
Publish changes as a new version. Avoid both discovery layouts for the same ID
and version because selection requires exactly one match. The launcher still
imports legacy `.chmod` ZIPs, whose entries start at the same folder root.

### File and JSON rules

- Package paths are relative, use forward slashes, and contain only ASCII
  letters, digits, underscores, dots, slashes and hyphens. The limit is 220
  characters. Reject traversal, empty segments, trailing dots or spaces,
  Windows devices, case-insensitive collisions, links and junctions.
- Use UTF-8 JSON, exact case-sensitive property names and no additional keys.
  Reject duplicate keys, including case variants and escaped equivalents,
  trailing commas and nesting deeper than 32 containers. The manifest limit is
  1 MiB. All SHA-256 values are 64 lowercase hex digits computed over file bytes.
- A package supports up to 4,096 asset entries and 8,192 tree entries. Keep
  total declared payload size at or below 512 MiB. Ordinary asset and uniform
  files have a 128 MiB individual limit. A roster file, roster header or native
  DLL has a 64 MiB individual limit. Use the validator for narrower media bounds.

## Manifest

| Field | Authoring rule |
| --- | --- |
| `schema_version` | JSON integer `1`. |
| `id` | Stable lowercase identifier matching `^[a-z0-9]+(?:[.-][a-z0-9]+)*$`, up to 512 characters in the manifest, with installed path limits also applying. |
| `name`, `author` | 1–120 characters with no ASCII control characters. |
| `description` | Optional text up to 4,096 characters. |
| `version` | Numeric `MAJOR.MINOR.PATCH`. Each component is zero or starts with a nonzero digit. |
| `requires` | Exactly `xex_sha256`, `recomp` and `mod_api`. Use the pinned Xbox title revision below. |
| `content` | Exact set of `assets` when asset entries or new uniforms exist, `rosters` when a roster exists, and `code` when an extension exists. At least one class. |
| `capabilities` | Exact union of the asset kinds, `uniform.register` if present, `roster.expose` if present, and the extension's required capabilities. Emit each once. |
| `dependencies` | Array of exact `{id, version}` pairs. No self-reference, duplicates or cycles. |
| `incompatible` | Array of conflicting mod IDs. One side declaring the conflict is sufficient. |
| `assets` | Always present. Use `[]` when the package has no existing-resource replacements. |
| `roster`, `uniforms`, `extensions` | Optional feature-specific sections described below. |
| `update_source` | Optional object with `url` pointing to the mod's GitHub repository releases path. Omit for local authoring. |

Generate this requirement block for current exports:

```json
{
  "xex_sha256": "71e8983d1cc009e485696aad19b5fa4b4661761870e2c8972717b932c1e4be36",
  "recomp": "ZMO-beta1",
  "mod_api": "1.3.0"
}
```

The launcher accepts API versions 1.0.0 through 1.3.0. API 1.0 is DDS-only.
Cloth positions and native roster exposure date to 1.1, uniform registration
and legacy ABI 1 extensions to 1.2, and court scenes, shorts simulation, ABI 2
and conditional Button Style DDS to 1.3. An editor should default to 1.3 and
verify the specific feature against the selected installer's tools.

### Complete manifest example

This example uses the verified Georgia Southern base-floor DDS identity from
the current loose installation. Re-read the identity and source digest from
the user's installation and replace the final hash token with the SHA-256
of the exported DDS. This route keeps the stock court markings in place.

```json
{
  "schema_version": 1,
  "id": "author.hanner-floor",
  "name": "Hanner Fieldhouse Floor",
  "author": "Author",
  "version": "1.0.0",
  "requires": {
    "xex_sha256": "71e8983d1cc009e485696aad19b5fa4b4661761870e2c8972717b932c1e4be36",
    "recomp": "ZMO-beta1",
    "mod_api": "1.3.0"
  },
  "content": ["assets"],
  "capabilities": ["dds.replace"],
  "dependencies": [],
  "incompatible": [],
  "assets": [
    {
      "kind": "dds.replace",
      "bank_hash": 1171464608,
      "record_index": 9,
      "record_id": 3192247854,
      "record_type": 3798768477,
      "texture_slot": 0,
      "target": "assets/s272.iff/floor.scne/floor_diffuse_8fc00df1.dds",
      "source_sha256": "5952b1cadf71a63f900d472ebee2d0ac457458b5727f2c1958d5ea4f6bcd46ea",
      "file": "assets/s272.iff/floor.scne/floor_diffuse_8fc00df1.dds",
      "sha256": "<replacement DDS SHA-256>"
    }
  ]
}
```

## Existing-resource entries

Each `assets` item has four unsigned 32-bit JSON integers `bank_hash`,
`record_index`, `record_id`, `record_type`, and four strings `target`,
`source_sha256`, `file`, `sha256`. The optional `kind` defaults to
`dds.replace`. The only other optional fields are `component`, `texture_slot`
and `selection`, admitted as described below.

`target` names the installed resource. `file` names the payload in the
exported package. `source_sha256` binds the original DDS or decoded component.
`sha256` binds the replacement bytes. Copy the bank hash from the installation's
`assets.json`. Copy the record tuple from that bank's `asset.json`, using
`paired_resources` when present and `records` otherwise. The record index
disambiguates repeated IDs. Follow the install's `asset_path_aliases.json` for
known older paths. Present verified names in the editor and retain hashes and
types as identifiers, including for resources with no recovered name.

| Format | `kind` | `record_type` | Required asset fields beyond the common fields |
| --- | --- | ---: | --- |
| Standalone texture | `dds.replace` | 1547079785 | None. Add `selection` only for Button Style. |
| Named embedded texture | `dds.replace` | 1547079785 or 3798768477 | `texture_slot`, integer 0–4095. |
| Cloth mesh positions | `cloth.positions` | 3798768477 | `component: 0`. |
| Shorts simulation | `cloth.simulation` | 3776073491 | `component: 0`. |
| Court floor | `court.scene` | 3798768477 | Two entries, `component: 0` and `component: 1`. |

### Standalone DDS

Use `assets/<bank>.iff/<record>.txtr/texture.dds` as the target. Obtain the
source digest from the bank's `textures` metadata and confirm it against the
original DDS. The payload can have its own name under `assets/`. Retain the
Xbox template's compression and aspect ratio. The native replacement path
accepts supported BC formats and same-size or integer power-of-two upscales
through 8,192 pixels per axis, with a single level or a valid mip chain.
Use the native validator's result for the exact template. Conflicting
replacements for a shared original pixel identity reject, even when their
targets are in different banks.

This route covers existing jerseys, shorts artwork, shoes, logo plates and UI
atlases where the installation catalogs them as supported standalone TXTRs.
An existing uniform texture replacement needs neither new uniform registration
nor a roster when the roster already selects that resource.

### Named DDS slot

Look up the bank and record in `scene_textures.json`, then select the entry by
`slot`. Use its catalog `file` as **both** `file` and `target`, and its
`sha256` as the source digest. Typical layout:
`assets/s272.iff/floor.scne/floor_diffuse_8fc00df1.dds`.
Use the catalog file field even if the editor shows a different presentation
name. An exact slot can belong to either an IFF or CDF folder.

The editor should retain the original base-level dimensions, encoding, face
count and expected mip layout. These images are written back into their owning
resource and are subject to that resource's capacity, format, palette and
overlap checks rather than the standalone upscale policy. Use the native
exported DDS as the template. Indexed number sheets retain the Xbox palette
and untouched mips and have only the palette capacity reported by the writer.
Expose lighting, bump and reflection textures under their catalogued support
paths. DDS entries do not take `component`, and named slots cannot be conditional.

### Cloth mesh and simulation

For `cloth.positions`, use the stock one-component SCNE's `scene.dat` or
supported legacy `block0.dat`. Export a same-size component with edits
restricted to verified unquantized Xbox float3 positions. Indices, stream
declarations, formats, materials, normals and UVs retain their original bytes.
For the pinned combined `benplay.scne` mesh the validator restricts edits
further to shorts-draw Y positions and an upward displacement of up to 12 units.
An editor should expose a hem control for that layout.

For `cloth.simulation`, bind a named
`assets/cloth_shorts.iff/shorts{fat,reg,thin}.e1124f13/resource_data.dat`
component. The native validator pins the supported source hashes and permits
bounded edits to the 800 packed rest-position Y values and active Xbox
distance-constraint lengths. Preserve the endpoints, flags, scheduling and
other bytes. A height control that changes simulated shorts should produce the
matching render and simulation edits for each body style. Check the separate
`benplay.scne` geometry when authoring a matching hem for that model.

### Full court

Use two entries sharing one bank hash and record tuple for the floor SCNE
`be45d62e` / 3192247854. CPU is component 0 and targets `scene.dat`. GPU is
component 1 and targets `scene_gpu.dat`. Legacy `block0.dat` and `block1.dat`
paths are recognized when mapped to the owning components. Bind both original
digests and stage both files together.

For a one-image court tool, call
`ch2k8_tools build-full-floor GAME s###/artwork.dds MODS` when provided by
the installed version. The input is a 2048×1024 BC1/DXT1 DDS with 12 mip levels
and the UGA artwork layout. It generates the two Xbox components and their
versioned mod manifest. It maps the artwork to the verified stock UV layout,
hides decorative draws and retains the stock lighting geometry. Use
`audit-full-floors GAME` to populate the editor's court selector on builds
with that command. Split and unrecognized courts require their own conversion.
Older tools with `validate-court` may support only the pinned UGA layouts.
Use the named DDS route for a repaint that keeps a compatible court's original
geometry and markings.

## Native roster

Use the `rosters` content class and the `roster.expose` capability. The
optional `roster` object has exactly `file`, `sha256`, `header` and
`header_sha256`. Put the actual Xbox payload at `rosters/Roster.ROS` and
the matched native aggregate header at `rosters/Roster.ROS.header`.
The payload starts with a big-endian length of its remaining bytes and the
header is 328 bytes. The validator checks the observed Roster.ROS name,
title `54540818`, Dummy HDD device 1, saved-game type 1, neutral aggregate
XUID and native table relationships. Use the Studio
native roster exporter or an actual compatible save/header pair as the source.
Loose game ROST components, CSV and editor project files are intermediate
formats. Only one roster package can be active. Native roster and code selections
derive isolated user-data profiles. The package has no arbitrary save-path field.

## New uniform pairs

Use content `assets`, capability `uniform.register`, and optional
`uniforms` containing 2–64 bank objects. Each has exactly `name`,
`template_hash` (uint32), `template_layout_sha256`, `folder` and `files`.
The layout digest is for the matching stock template's `asset.json`.
`folder` is `uniforms/<name>`. `files` lists 2–4,096
`{path, sha256}` objects whose paths are relative to the individual bank
folder, including its source-bound `asset.json`, component files and DDS
payloads required by the template. The runtime derives the active bank layout.

Create a world/selection pair in the same package, for example `ux123.iff`
and `selux123.iff`. Use the correct template for each half. The letters
`h/a/x/y/z` mean Home, Away, and Alternates 1/2/3. Use canonical artwork IDs
0–1023 padded to at least three digits. Artwork ID is separate from team and
roster owner IDs. New Home/Away banks require a same-package native roster
with a matching route assigned to a team. Alternate-only pairs can link at
launch through unique existing native artwork ownership. Unresolved owners,
occupied slots, bank collisions and ambiguous texture identities reject.
Only validated template-compatible art modifications are supported. Edit
added banks inside their `uniforms/` inventory rather than through ordinary
`assets[]` overrides.

## Native extensions and Button Style

Use content `code` and an `extensions` array of exactly one Windows x64 DLL
entry. The module path is `code/<file>.dll`. The ABI 1 entry has exactly
`file`, `sha256`, `abi: 1`, and `hook: "player.weight.read"`. Its
capability is `hook.player.weight.read`. ABI 2 requires API 1.3 and exactly
`file`, `sha256`, `abi: 2`, `capabilities`, and `replacements`.
Use a nonempty capability array and a replacement array of zero to two allowed
semantic hook IDs. Include each extension capability in the top-level union.
Use the [hook registry](hook_registry.json) and [SDK ABI](../../sdk/include/chmod/abi.h)
for signatures, phases, feature discovery and code generation. The only
replacement claims are `player.weight.read` and `player.weight.write`,
each requiring its corresponding extension hook capability.

Button Style combines one ABI 2 provider of `hook.presentation.button_style`
with standalone DDS entries whose `selection` is
`presentation.playstation`. IDs below are hexadecimal for lookup; write
them as decimal JSON integers. `global.iff` has bank hash 3680386632 and
`gamedata.iff` has bank hash 1823768513.

| Bank | Index | Record ID | Use |
| --- | ---: | --- | --- |
| global.iff | 270 | 7542283f | Required primary prompts |
| global.iff | 410 | acc6d118 | Required stick directions |
| global.iff | 0 | 001d1bcf | Optional small controller icon |
| global.iff | 190 | 4ffa5eb9 | Optional controller icon glow |
| global.iff | 512 | d948c961 | Optional navigation prompts |
| gamedata.iff | 142 | 969565e4 | Optional on-court icon passing |

Select Xbox or PlayStation in the native Presentation menu. The editor exports
the PlayStation payloads and the provider, while the runtime supplies Xbox
fallback. Older runtimes may accept fewer conditional entries. Check executable
and GPU DLL compatibility. The launcher verifies the executable,
`rexruntime.dll` and `rexgpu-xenos.dll` against the runtime receipt for
Button Style. Native DLL execution requires user opt-in. Import,
preview and metadata validation must never load a package DLL. Hooks for
unresearched game rules, Legacy events, or arbitrary addresses are outside the
current API.

## Editor export and preflight

1. Open a pristine Xbox loose install and verify its `default.xex`, platform
   and storage. Index banks, records, decoded component ownership, aliases,
   DDS slots and source digests. Keep the workspace separate from the install.
2. Let users combine supported features in one project. Build the exact
   manifest inventory and capability union from the selected features. Resolve
   the source identity and hash before encoding each payload.
3. Produce the complete package in temporary storage. Hash the final bytes
   and write `mod.json` last. Reopen the exported package with the same
   loader rules. Report the offending bank, record, slot or component on error.
4. Use the production tool for semantic preflight. Available validators include
   `validate-cloth ORIGINAL REPLACEMENT`, `validate-cloth-rest ORIGINAL
   REPLACEMENT`, `validate-court SOURCE_CPU SOURCE_GPU EDITED_CPU EDITED_GPU`,
   `validate-roster PAYLOAD HEADER` and `validate-uniform GAME PACKAGE_BANK
   TEMPLATE_HASH NAME TEMPLATE_LAYOUT_SHA256`. Use the launcher's `Read-Chmod`
   and `Resolve-Chmods` to check package and selection rules. A successful
   dry stage checks renderer asset identities and component maps.
5. Import or publish the versioned folder. The user selects an exact version
   from Mods. Enable lists run low to high priority. Only ordinary DDS
   replacements for an identical target use last-wins priority. Whole-scene
   overlaps, scene-vs-slot overlaps, conditional DDS overlaps, competing
   roster packages and exclusive hook or uniform claims reject. The launcher
   stages in a private cache and changes take effect after restart.

Launcher state lives at `port/userdata/mods.json` and has `version: 1`, an
`enabled` array of exact `{id, version}` entries, and optional native opt-in
`allow_native_code`. Keep this file outside the mod package. Use the launcher's
selection controls so the editor can export a folder without enabling it or
changing the user's trust settings.

The editor can preview arbitrary game resources, but export should be enabled
only for a path backed by a current capability. Materials, DDS, native
rosters and published typed hooks have separate export contracts. Raw archive
swaps, generic SCNE topology changes, audio, animation, LAYT editing and
arbitrary DAT overrides have no general CHMOD folder capability today.

### Alternate uniform neckline

A registered world alternate bank may include `neck_shape` in its uniform
manifest entry. The integer maps to U, V, V triangle, Triangle, or Wishbone
for values 0 through 4. Unspecified necklines inherit the Home row when the
launcher adds a route. A specified neckline replaces the shape bits while the
rest of the Home characteristics carry over. The selection bank uses that same
route. With active mods the launcher enables installed alternate pairs and
clears existing uniform unlock codes in supported native roster saves.

New uniform banks may also override the validated indexed `jersey_numbers` and
`names` mip and palette data. The bank retains the original glyph metrics and
aligned layout.

### Stock uniform replacement

A world/selection pair can replace existing stock banks when each
`template_hash` is the hash of the exact target name and the layout digest
matches that bank. The validator retains the stock bank IDs and isolates BC
texture identities in the mod overlay. Replacements keep the routes in the
active roster and do not require a packaged roster. Overlapping whole-bank
replacements and loose DDS overrides for the same bank are exclusive.

### Nested collections

Drag a collection folder into the Mods window or use **Install mod or collection**.
A collection contains child package roots with their own `mod.json`, nested
under optional category directories. Folder names can contain spaces. Install
preserves the hierarchy and validates each child independently, including its
512 MiB package limit. There is no aggregate 512 MiB limit for a collection.
Select a folder row to enable or disable the newest version of each child
mod together. Select a child row to control its version and priority.
