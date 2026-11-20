# Recent ZMO beta research and integration record

This index consolidates the recent asset/modding, presentation and portability
work. It records implementation evidence separately from proposals and pending
manual checks. The beta is the review source for the main-branch PR.

| Area | Source and evidence |
| --- | --- |
| Named loose assets and separate DDS ownership | [Loose assets](../formats/loose_assets.md), [paired components](../findings/2026-11-02-paired-components.md), [native texture memory](../findings/2026-11-02-native-texture-memory.md) |
| Folder packages and editor contract | [Modding guide](../MODDING.md), [export specification](../formats/mod-folder-editor.md), [schema](../formats/chmod.schema.json) |
| Native extension research | [Framework findings](../findings/2026-11-08-extension-framework.md), [SDK](../../sdk/README.md), [acceptance](../CHMOD_ACCEPTANCE.md) |
| Courts, shorts and icon overrides | [Court findings](../findings/2026-11-12-chmod-court-scene.md), [loader audit](../findings/2026-11-12-modloader-audit.md), commit `0087e9f` |
| Full-court builder | `47999d4`, native floor audit/builder and editor export contract |
| Alternate uniform routing and stock overlays | `896b98b`, `4465c6d`, uniform contracts and launcher activation |
| Recursive collections and folder selection | `1f0399c`, `tools/chmod.ps1` discovery/install and `tools/chmod_ui.ps1` selection |
| PS3 scorebug geometry, shaders and live overlay data | `cddc984`, [detailed findings](../findings/2026-11-19-scorebug-elements.md), `tools/scorebugs/`, `ghidra/DecompileScorebug.java` |
| macOS feasibility and remaining platform dependencies | [Portability assessment](mac-portability.md) |

The current main branch already contains earlier beta integration, including
native court lighting, shorts constraints, recovered naming and hook framework
work. The PR adds all remaining beta commits rather than duplicating earlier
history. Studio source belongs to its separate repository; this repository carries
the loader/editor interchange contract and native tools.

## Recent-chat boundaries

The PS3-to-Xbox roster conversion chat is active research. It identifies different
player record sizes (308 bytes PS3 versus 316 bytes Xbox) and is investigating
field parity. No completed one-to-one roster converter or face/morph mapping is
claimed or included by this integration. Preserve native Xbox validation until
that separate work provides reproducible evidence.

The RPCS3/recomp assessment recommends sharing authoring assets and retaining PS3
as a reference while verifying playable parity, Legacy saves and platform access.
It is a development recommendation, not evidence that PS3 saves, shaders or geometry
are directly interchangeable with Xbox data.

## Acceptance still needed

The scorebug findings record successful build and structural audits for both
styles. New logo alpha, placement, live elements and match transitions still need
the owner's manual gameplay check. Live poll-rank fields remain unresolved.
No macOS build has been validated. Older findings retain their dated acceptance
status and should be read with the newer feature-specific evidence.

Only source, documentation and reusable research scripts belong in this PR.
Original game executables, extracted assets, source art, converted scorebug banks,
user saves, runtime caches and third-party mod archives remain local.
