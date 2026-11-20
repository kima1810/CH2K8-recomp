# ZMO modloader, hook and performance research

This index covers implemented loader updates and recorded reverse-engineering
and performance evidence. Mod packages and proposed platform/features are outside
this integration. Existing main-branch work is linked as context.

## Modloader updates

| Area | Source and evidence |
| --- | --- |
| Folder packages and editor interchange | [Modding guide](../MODDING.md), [export contract](../formats/mod-folder-editor.md), [schema](../formats/chmod.schema.json) |
| Recursive collections and folder selection | `tools/chmod.ps1` Find-ChmodFolders/Install-ChmodCollection and `tools/chmod_ui.ps1`; per-package limits remain enforced |
| Uniform registration and source-bound overrides | `tools/native_assets/uniform_contracts.h`, `tools/chmod.ps1`; world/selection pairing, layout digests and roster ownership checks |
| Court component validation and authoring tools | `tools/native_assets/court_contract.h` and `full_floor_builder.h`; paired components retain supported lighting geometry |
| Launcher compatibility, recovery and profiles | [Loader audit](../findings/2026-11-12-modloader-audit.md) |
| Named resources and texture ownership | [Loose assets](../formats/loose_assets.md), [paired components](../findings/2026-11-02-paired-components.md) |

## Hook research

The [native framework findings](../findings/2026-11-08-extension-framework.md)
and [SDK](../../sdk/README.md) describe typed registration, lifecycle, capability
negotiation and native ownership. [Presentation button-style research](../findings/2026-11-08-presentation-button-style.md)
records the native menu path. [Scorebug research](../findings/2026-11-19-scorebug-elements.md)
records scene initialization, native labels/timeouts/fouls/bonus/possession fields,
text/material draw boundaries and platform scene-format differences. The Ghidra
script is included for reproducible inspection. A public scorebug API is not added.

## Performance updates and evidence

[Staging performance](../findings/2026-11-20-mod-staging-performance.md) documents
cache reuse, sparse overlays, staging progress and remaining synchronous work.
These are implemented paths, with no new boot-time or full-overhaul benchmark.

Earlier renderer/runtime changes are already in main:

- [Native GPU progress waits](../findings/2026-11-03-native-gpu-progress-wait.md).
- [Geometry kernels](../findings/2026-11-03-native-geometry-kernels.md) and
  [packed-vector lane research](../findings/2026-11-03-packed-vector-lane-order.md).
- [Native texture memory](../findings/2026-11-02-native-texture-memory.md).
- [Pause GPU backlog](../findings/2026-11-01-pause-menu-gpu-backlog.md).
- [Guest refresh timing and adapter selection](../findings/2026-11-07-rapid-lag-display-and-adapter.md).

Each dated finding carries its own verification scope. Compilation, structural
audits and a limited smoke run do not establish general FPS improvements.
Scorebug hook behavior still needs manual gameplay validation; live poll ranks
remain unresolved. No game was launched for this documentation revision.
