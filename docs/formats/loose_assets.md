# Xbox folder assets and native DDS

For packaged source-bound DDS/cloth overrides and isolated native roster saves,
see the [current CHMOD package profile](chmod-1.1.md) and its
[implementation evidence/status](../findings/2026-11-08-chmod-backend.md).

The beta launcher uses native `ch2k8_tools.exe` for ISO import and resource preparation. For the standalone Windows beta package and tester workflow, see [BETA.md](../../BETA.md) and the [portability validation](../findings/2026-11-02-beta-portability.md). The older folder packager described below remains a checkout-oriented developer tool.

## Current direct-folder build (2026-11-02)

The current CLI import creates `storage: loose-resources` installations. Resource
bodies are read directly from decoded folder components; packed `.stored` blocks,
physical archive parts and assembled asset-cache binaries are not required.
`_runtime` contains small compatibility headers, padding and validation metadata
for the existing guest loader, not rebuilt asset payloads. The legacy scatter-map
workflow described below remains supported; its `.stored`, `_archive`, `_cache`
layout and recompression instructions describe that older mode only.

`tools/enable_direct_assets.ps1 -GameData PATH` migrates existing installation
metadata with a backup and rollback on failure, without launching the game.
Preparation automatically selects direct mode for modern imports. Packaging still
uses `tools/package_loose_game.ps1`; its launcher depends on this source checkout.

The source now also accepts validated BC4/BC5 DDS layouts (ATI1/ATI2), discovers
supported resource sidecars, and supplies fixed-duration native PCM WAV substitution
through the patched SDK. WAV edits must retain PCM16, channels, sample rate and
sample count; looping XMA streams fall back. `--ch2k8_native_audio=false` disables
audio substitution. These additions require manual in-game acceptance testing.

`asset_edits.json` supports checked added uniform banks and native edit bindings.
Added banks rebuild virtual sorted loader metadata without physical archive parts.
Most component sizes remain fixed. The sole growing-roster exception requires one
ROST record owning its entire sole component, non-shrinking even length and a
64 MiB maximum. This structural exception does not validate semantic roster fields.
Arbitrary growth, arbitrary new filenames and semantic editing remain unsupported.

The historical byte-identical archive evidence below applies to the legacy mode.
Direct mode has synthetic component-read/import regression coverage; it has not
been established to reproduce packed archive bytes or to work in live gameplay.

The recomp's read-only VFS can serve the original archive address space from
individual folder files, without physical `0A`–`0M` chunks. The Xbox game still
interprets IFF/SCNE/ROST data; this is not a replacement scene/roster engine.
Only Xbox assets are imported. CH Extractor documentation supplies the folder
and preservation baseline, not PS3 artwork or PS3 texture conversion rules.

## Build/import

The portable ZMO beta launcher now offers **Import ISO...**. It converts the
selected ISO directly into a new `loose-resources` installation, including
decoded components, supported DDS templates and runtime maps. It does not mount
the ISO or stage the original archive chunks. Python 3.11+ is required. The
launcher displays progress, supports cancellation between asset operations,
and publishes the installation only after preparation succeeds. Failed imports
remove only their own temporary directory. Existing destinations are refused;
later launches use the completed folder without importing again.

Build/install the patched source SDK with `tools/build_vulkan_sdk.ps1` and build
the `win-amd64-vulkan` game preset (which supports D3D12 too). **Native DDS is
currently D3D12-only.** The original Vulkan texture path remains available.

From the repository root:

```powershell
port/out/python-env/Scripts/python.exe tools/loose_assets.py import 'PATH/TO/GAME.iso' port/out/folder-game
# An extracted Xbox disc directory is also accepted.
powershell -NoProfile -File tools/package_loose_game.ps1
```

ISO members are read directly without staging archive chunks. Import refuses an
existing destination. `assets.map` is published after extraction; an interrupted
import without that map is incomplete. Never import over the source directory.
Alternatively configure CMake's `CH2K8_GAME_SOURCE` and optionally
`CH2K8_ASSET_DESTINATION`, then build `ch2k8_import_assets`.

Packaging copies the executable/DLLs alongside the folders and writes
`Launch Folder Game.cmd`. It does not launch anything. This local entry uses the
source checkout's launcher/Python environment. Open it and click Launch yourself.

## Layout

```text
folder-game/
  ch2k8.exe, rexruntime.dll, rexgpu-xenos.dll, default.xex
  Launch Folder Game.cmd
  assets.json                  archive identities/provenance
  assets.map                   runtime scatter map
  native_dds.index              original-pixel-to-DDS catalog
  assets/
    s258.iff/                  bank directory
      asset.json
      archive_header.dat       preserved Xbox IFF header
      floor.scne/
        record.json
        scene.dat              decoded CPU component and scene descriptors
        scene_gpu.dat          decoded GPU component
        diffuse_49977575.dds   DDS base level with sampler role and texture ID
    teamselectlogo.iff/
      logo000.txtr/
        record.json
        texture_header.dat
        texture_pixels.dat
        logo000.dds
    hash_<archive-hash>.iff/    stable fallback for unresolved names
  _archive/                    original TOC/alignment/opaque bytes
  _cache/                      per-IFF overlays and validation receipts
```

Record suffixes include SCNE, TXTR, ROST, LAYT, NAME, CDAN and AUDO; unknown types
retain numeric hashes. Numeric IDs avoid invented names. Shared component ranges
are stored once under their first owner. `asset.json` gives their offsets/paths.

## Resource editing

Close the game, edit the named decoded components, then launch through the
provided entry. Older imports use `blockN.dat` filenames. The launcher prepares changes before starting the game. **Keep component
lengths unchanged.** SCNE data, texture descriptors/pixels, roster bytes and other
records remain editable. This is a binary interface, not a semantic GUI or JSON
roster editor. `record.json` is descriptive; changing it does not edit the game.

Preparation recompiles only changed IFFs. It preserves opaque bytes, record
positions, unrelated blocks and trailers. Raw blocks remain raw, ZLIB remains
ZLIB, and H7A uses literals while preserving its opaque wrapper fields.
A small virtual TOC updates offsets/sizes. The last virtual part may grow up to
the original first-part size, retaining the 13-part address model. No physical
archive chunks are rebuilt. Unknown/non-standard containers retain `payload.dat`
for whole-file replacement by a format-aware editor, including size changes.
Paired IFF/CDF edits must remain consistent.

Growing individual records, adding records or changing internal pointer/count
relationships requires a validated format-aware writer and is not supported by
this bridge. PS3 roster offsets must not be assumed to apply to Xbox records.
Do not edit `.stored`, `_archive`, `_cache` or manifests. Back up your edits;
reimport into a different directory to recover original copies.

Preparation alone, without launching:

```powershell
port/out/python-env/Scripts/python.exe tools/loose_assets.py prepare port/out/folder-game
```

Successful validation caches size/timestamps/digests. A single directory snapshot
rejects symlinks/junctions and avoids repeatedly resolving every path. Changed files are validated
again; delete `_cache/validation.json` for a full rescan. Prepared data/header
filenames are content-addressed and the map is published after validation.
Restart after edits. Hot reload and preparing while the game runs are unsupported.

## Named scene and texture resources

Launcher imports use the Xbox header to assign a resource type to each
record. Known names are matched against their original resource ID. The
installed court at `assets/s258.iff/floor.scne/` contains `scene.dat`,
`scene_gpu.dat`, and the floor DDS files. When an exact texture name is
missing, filenames use the shader sampler role where it is unambiguous and
include the original texture ID. Other records use their type and ID as a
fallback. Shared component files retain one physical copy.

The paired `teamselectlogo.iff` bank contains 520 `logoNNN.txtr` folders
with the original numbering. Each folder contains the editable DDS, the texture
header, and Xbox pixels. Inline TXTR records use `texture_inline.dat` for the
combined source component. The map still serves each component at the offset specified
by the paired header. LAYT, ANIM, CDAN and other recognized resource types
retain their header type in the folder name.

The native launcher converts edited DDS base levels back into the owning
runtime component. Keep the format, dimensions, face count and a single mip
level. Indexed Xbox textures such as jersey numbers use an RGBA8 DDS for
editing. The writer retains their Xbox palette and other mip levels
and accepts new colors when unused palette entries are available. The CTX1
DDS uses an Xbox-specific FourCC and requires a CTX1-capable editor.
The catalog records the resource ID, descriptor offset and Xbox fetch format,
and reports unsupported layouts. Use
`ch2k8_tools organize-assets GAME_FOLDER` on a copy of an existing
installation to apply this layout and migrate existing DDS edits.

For a named SCNE, the exporter follows validated draw runs to materials and
texture samplers. It uses an unambiguous geometry name when the scene preserves
one. Texture IDs distinguish shared or unnamed materials. Lighting and other
recognized shader data are placed in `_support/` and retain their Xbox layout.

To present the editable artwork of every floor as PNG, run
`python tools/court_artwork.py present GAME_FOLDER` after organizing the
assets. PNG names use the verified geometry and sampler where available, with
the original texture ID kept in the filename. LSU uses the same naming, for
example `centerlogo_diffuse_a37a1e3d.png`. Data textures, including cubemaps,
remain under `_support/` in their original DDS formats.

PNG editing uses Pillow and a sibling CHoops-Extractor-Reborn-Recomp checkout
for native texture conversion. Keep the original image dimensions and channel
layout. The launcher synchronizes edited PNG pixels into the original Xbox
encoding. Keep `court_artwork.json` and the backing DDS files under
`_runtime/court-artwork` with the installation. The earlier LSU-specific
manifest and backing files are supported when migrating an existing install.

## Native DDS

Supported TXTR base levels export as legacy DDS DXT1/DXT3/DXT5 (BC1/BC2/BC3),
including inline and split CPU/GPU resources. Preserve the BC format/aspect ratio.
The original size or integer power-of-two upscales up to 8192 pixels on either
axis are accepted, with one level or a valid mip chain. Exported templates contain
the original base level. **Unchanged templates retain the game's original mip
chain.** Generate mipmaps when saving replacement artwork to reduce shimmer.
Upscaling artwork is an external editing step; import does not create new detail.

Unsupported formats, non-block-aligned BC sizes, stacked/cube/volume resources,
and base levels in packed mip tails retain editable raw data. `asset.json` lists
the reason. DX10 DDS, format
changes, downscales, arrays and cubes are rejected rather than guessed.

Only edited DDS files enter the active catalog, avoiding stock texture hashing.
At upload, D3D12 matches original dimensions/format and a canonical pixel-block
hash using guest pitch/tiling/endianness. Edited DDS goes directly to a host texture,
bypassing guest retiling and conversion compute. The guest allocation retains its
original size. Native views use the replacement's mip count and guest swizzle.

Identity is independent of transient addresses. Identical original textures cannot
yet be distinguished by owning IFF at bind time: conflicting DDS replacements for
one original identity are rejected. Give identical sources identical replacements.
Removing this restriction needs additional asset-owner tracking.

GPU-written/resolved ranges are excluded. Memory invalidation reevaluates identity
and restores the original resource for a non-match. Old native resources/descriptors
remain alive until their submission fence completes and are reclaimed on texture
requests or normal cache teardown; staging buffers expire after their submission
completes. Invalid runtime DDS falls back with a logged error. Successful
uploads appear as `Native DDS upload` in the runtime log.

`--ch2k8_native_dds=false` disables native substitution while retaining the folder
loader for a manual control test. DDS is cached within a run; restart after edits.

## Offline checks and user test

These standalone tools do not load an XEX or game code:

```powershell
port/out/build/win-amd64-vulkan/ch2k8_assets_check.exe verify port/out/folder-game work/ch2k8/XBOX/disc
port/out/build/win-amd64-vulkan/ch2k8_vfs_check.exe port/out/folder-game
port/out/build/win-amd64-vulkan/ch2k8_assets_check.exe catalog port/out/folder-game
port/out/build/win-amd64-vulkan/ch2k8_assets_check.exe gpu
```

The GPU tool uses the exact shared runtime upload helper, compares every mip byte
after hardware/WARP readback, and checks native dimensions. This proves uploads,
not in-game visuals. The user should test an unchanged-folder boot, gameplay,
2K Nav/replay, a visible DDS edit, an upscale with mipmaps and a known safe SCNE/ROST
field edit. Check native upload log lines. The game was not launched during work.

## Baseline references

### Paired component update

Fresh direct imports split paired CPU/GPU resources into decoded component files,
preserving unclaimed gaps and shared identities. No original combined paired
payload is required afterward. Existing-install conversion retains backups by
default. See [paired component evidence](../findings/2026-11-02-paired-components.md)
for preservation checks, interrupted-conversion handling and gameplay limits.

Read-only CH Extractor sources: `docs/TEXTURE_CONVERSION.md`,
`docs/ROSTER_EDITOR.md`, `choops_py/archive/folder_import.py`,
`formats/standard_iff.py`, `formats/compression.py` and its DDS workflow. Their
preservation policy, owning-IFF folders, DDS priority and relocation restrictions
inform this interface. The PS3 converter is not reused. Xbox layout comes from
the pinned ReXGlue/Xenia fetch/texture implementation.
