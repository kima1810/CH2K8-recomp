# Mod code and asset overlays

Mods must work with an unmodified game executable and pristine vanilla assets.

- **Code mods ship as DLL patches.** Load the DLL through the modloader with native-code opt-in. Apply code patches at runtime in memory. Keep mod-specific code out of the executable and its source and build configuration. A mod install or launch must never overwrite or patch the executable on disk.
- **Asset mods ship as overlays.** Package replacement assets for the modloader to resolve over the vanilla assets. Package new assets alongside them through the overlay. Keep generated files in the mod package or its own staging directory. A mod install or launch must never change files in the vanilla asset directory.
- **Disabling a mod restores vanilla behavior.** Launching without the mod must omit its DLL and asset overlays. Installing, updating, or disabling a mod must require no restoration of vanilla files.

Verify each release against a clean baseline. Check that the executable and vanilla asset hashes are identical before installing the mod, after running with it, and after disabling it.

## Package format and loading

Distribute loose folders with a `mod.json` manifest. A ZIP may be used for delivery. The installer validates and extracts it once, and the launcher and game use the installed files and prepared overlay. ZIP decompression stays outside the gameplay loading path.

Ship only new and changed payloads. Resolve unchanged assets from the vanilla install. Split large projects into independently versioned roster, uniform, court, presentation and audio packs. Use a collection when they should be selectable together. Current limits apply to each child package. See the [editor export contract](formats/mod-folder-editor.md) for limits, source identities, hashes and dependency rules.

Resolve the full selection before activation. Reuse a prepared overlay when the vanilla source, selected versions and priorities, payloads and preparation tools match. Stage updates separately and retain the last working selection when preparation fails. Keep overlays, caches, native saves and authored source files in separate locations. Cache removal must leave user saves and installed packages intact.

## Behavior mods

Use data first. Mod authors supply assets, layouts and supported bindings. A single project-maintained CHMOD DLL provides mod-specific runtime behavior behind typed interfaces. Distribute the DLL independently from content packs, require explicit native-code opt-in, and bind each release to the runtime builds it supports. Third-party packages in this plan contain data only. The existing native SDK remains documented for compatibility with older packages and for project development.

The current scorebug preview implements scene selection, menu integration and live HUD rendering in a separate [CHMOD DLL](../examples/scorebug_preview/README.md). It is an opt-in, Windows-specific preview bound to a matching executable. The next step is to make layouts, vector shapes, and live HUD bindings data-driven so a visual update requires only a content-pack revision. Keep vanilla read-only and keep mod-specific behavior outside the executable throughout that work.

## Content authoring and release checks

1. Start in Studio with a pristine, supported Xbox install. Keep working files outside the package. Export supported payloads with their verified resource IDs, source digests, dependencies and compatibility requirements. The [modding guide](MODDING.md) lists what can be exported today.
2. Test each package alone and in its intended collection. Check conflict handling, a fresh install, repeat launch, disabling, upgrade and rollback. Record the game revision, runtime, renderer, package versions, logs and observed result. Distinguish structural validation from in-game acceptance.
3. Treat a roster package as an initial native Xbox save. Apply it once to the selected save profile and let the game own subsequent changes. Verify native load, edit, save and relaunch. Verify the original profile remains available. Export edits as a new roster package when they should be distributed.
4. Keep the base audio path intact. For future soundtrack and arena music packs, accept MP3 as a distribution format and prepare compatible audio in the overlay cache. Measure decoded cache size and first-preparation time before release. Streaming compressed music is a later option if cache size warrants it. General audio import and track mapping are planned capabilities.

## Updates for a solo maintainer

- **Mod content.** Publish a new version under the same package ID when updating content. Record changed assets, dependencies and tested runtime versions. Use the existing GitHub release update mechanism where appropriate. Retain the previous package and save profile for rollback. Keep dependencies pinned to compatible versions.
- **Shared DLL.** Publish matching builds with the target executable hash, a compatibility list and verification notes. Keep the DLL version independent of art packs. Use a consistent publisher identity for signed native releases when available. Keep native opt-in visible.
- **Game runtime and tools.** Use separate, versioned GitHub release artifacts. The [runtime updater](RUNTIME_UPDATES.md) documents verification, activation and rollback. Activate updates as complete versions, preserve the preceding runtime, and keep mods, vanilla assets and saves in the installation's data directories.
- **Release order.** Stabilize installation, save persistence and rollback first. Ship the data-driven scorebug as the first example of the shared DLL contract. Add audio import after source-track mapping, cache behavior and in-game playback are verified. Community submissions and catalog governance are outside this phase.
