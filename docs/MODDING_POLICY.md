# Mod code and asset overlays

Mods must work with an unmodified game executable and pristine vanilla assets.

- **Code mods ship as DLL patches.** Load the DLL through the modloader with native-code opt-in. Apply code patches at runtime in memory. Keep mod-specific code out of the executable and its source and build configuration. A mod install or launch must never overwrite or patch the executable on disk.
- **Asset mods ship as overlays.** Package replacement assets for the modloader to resolve over the vanilla assets. Package new assets alongside them through the overlay. Keep generated files in the mod package or its own staging directory. A mod install or launch must never change files in the vanilla asset directory.
- **Disabling a mod restores vanilla behavior.** Launching without the mod must omit its DLL and asset overlays. Installing, updating, or disabling a mod must require no restoration of vanilla files.

Verify each release against a clean baseline. Check that the executable and vanilla asset hashes are identical before installing the mod, after running with it, and after disabling it.
