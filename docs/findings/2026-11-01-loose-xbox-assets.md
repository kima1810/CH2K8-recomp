# Xbox loose folders and native DDS substitution

## 2026-11-02 source update

The current source adds direct decoded-component loading, BC4/BC5 DDS support,
fixed-duration native PCM WAV substitution, added uniform-bank metadata and a
bounded whole-component roster-growth exception. See the current-build section
of [loose assets](../formats/loose_assets.md). The evidence below records the
earlier legacy scatter-map implementation; it does not establish live-game
acceptance or GPU/audio correctness of these newer extensions. No game launch
was performed while preparing the PR.

## Question

Can the recomp install Xbox assets into editable IFF/resource folders, load those
folders without physical archive chunks, and substitute DDS textures directly on
the host GPU? Preserve SCNE/ROST/other binary editing and do not launch the game.

## Method

Read the CH Extractor Studio texture/roster documentation and folder discovery,
standard IFF and compression implementations as the organizational baseline.
Read the pinned SDK's Xenos fetch constants, texture layout/tiling, D3D12 texture
cache, filesystem device/entry/file and kernel asynchronous read implementation.
The Studio checkout, PS3 assets and existing overrides were not changed/imported.

Implemented an Xbox ISO member reader and importer, a validated scatter map,
read-only synthetic VFS parts/root, per-record component edits and a native DDS
catalog/upload integration. The original XEX device/handles remain alive; game,
d and new physical-device opens resolve to the loose device. The initial host
mount avoids recursively enumerating the asset tree before the synthetic mount.

Native DDS matches canonical original BC pixel content rather than transient
addresses. The renderer preserves guest descriptors/allocations, uses host-sized
resources/SRVs, excludes GPU-written ranges, reevaluates invalidated textures and
retires resources/descriptors through the existing fence-safe texture lifetime.
Staging resources retire after their submission fence. DDS is indexed only when
edited, preserving stock mip chains and avoiding stock texture hashing.

## Evidence

- [CONFIRMED, offline] All 3,378 Xbox archive entries imported. There are 2,829
  standard IFFs, 40,621 decoded resource components, 5,732 BC DDS templates and
  8,921 TXTR records with explicitly recorded unsupported-layout reasons. Source
  record types include 1,550 SCNE and one ROST record, alongside many other types.
- [CONFIRMED, offline] The C++ runtime scatter reader reproduces all
  **6,492,522,496 bytes** of the original 13-part archive, including metadata,
  gaps, trailers, cross-part reads and EOF behavior. There are no physical archive
  parts in the installed game folder.
- [CONFIRMED, offline] The real SDK VFS opens all 13 parts via absolute, relative,
  case-insensitive and physical-device paths; directory enumeration, concurrent
  reads, partial EOF, EOF status and read-only behavior pass. No XEX is loaded.
- [CONFIRMED, offline] Direct ISO and extracted-disc archive headers match;
  legalpage, frontend_sync and roster_english complete IFF reads match, as do
  cross-part reads. No new physical chunks are staged by ISO import.
- [CONFIRMED, offline] 5,046 deduplicated original DDS identities validate with
  the native C++ parser. The active catalog is empty in the delivered stock
  installation; preparation activates actual edits. Conflicting DDS files for
  identical originals fail validation.
- [CONFIRMED, offline GPU] The shared runtime upload helper preserves every mip
  byte through upload/readback on the RX 6650 XT and WARP. Each tests BC1/BC2/BC3
  at 64x64 with seven mips and at 2048x2048 with one mip, with original dimensions
  half the native resource dimensions. This includes uploads larger than the
  SDK constant-buffer pool's fixed page size.
- [CONFIRMED, offline] Synthetic SCNE/ROST edits reparse/decode with untouched
  ranges/trailers preserved; resizing is rejected before publishing a new map.
  Same-size and larger native DDS edits leave guest archive bytes identical.
  Invalid DDS edits leave the previously valid catalog intact.
- [CONFIRMED, measured] Cached preparation falls from 54.75 seconds to 9.57 seconds
  after replacing repeated canonical path/stat operations with a bounded directory
  snapshot. Reparse points are rejected. This measures pre-launch validation,
  not gameplay FPS.
- [CONFIRMED] Patched source SDK, game and standalone verification tools build.
  Packaging copies matching executable/DLLs and validates launcher arguments at
  2560x1440 borderless/native D3D12 without launching anything.
- [CONFIRMED] Final repository tests: **102 passed, 1 skipped** in 72.64 seconds.
  The final VFS and synthetic hardware/WARP checks pass after staging; packaged
  executable/GPU DLL hashes match the built/installed versions.

## Conclusion and limits

[CONFIRMED, implementation/offline checks] The folder loader and native D3D12 DDS
path are implemented and packaged for manual testing. Instructions and exact
supported layouts are in [loose assets](../formats/loose_assets.md).

[UNTESTED IN GAME] No menu/gameplay/mod-visibility assertion is made for this new
build. The user explicitly prohibited game launch and will perform those tests.
GPU readback does not prove runtime asset matching or visual equivalence in game.

Native DDS currently supports validated 2D BC1/BC2/BC3 base layouts, original-size
or power-of-two upscales and valid mip chains. Vulkan native substitution, other
formats, cubes/volumes, packed base mip tails and SCNE-embedded DDS discovery are
not implemented. Those resources retain binary components. SCNE/ROST editing is
same-length binary editing; semantic GUI editing and arbitrary record growth are
not claimed. Non-standard/CDF resources retain whole-file payload replacement.
Identical source pixel identities cannot yet be disambiguated by owning IFF.

This compatibility bridge preserves the Xbox resource interpreter. It does not
remove all Xbox GPU/CPU overhead or claim a gameplay performance improvement.

## Manual test

Open the packaged `Launch Folder Game.cmd`, then test stock-folder boot/gameplay,
2K Nav/replay, a conspicuous DDS change, an upscale with mipmaps, and one known-safe
SCNE/ROST edit. Look for `Native DDS upload` log lines. Use
`--ch2k8_native_dds=false` for a folder-loader-only control. Restart after edits.
