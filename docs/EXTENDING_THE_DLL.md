# Extending the shared CHMOD DLL

The shared DLL owns live game behavior. Loose mod packs supply artwork, layouts,
and settings. The current starting point is the Windows x64 ABI 2
[scorebug provider](../examples/scorebug_preview/scorebug_preview.cpp), built as
`scorebug-preview.dll`. Add feature modules to that target while the shared
provider evolves. Keep the vanilla executable and asset installation read-only.
See the [modding policy](MODDING_POLICY.md).

## 1. Choose the hook

| Feature needs | Implementation |
| --- | --- |
| Artwork or settings the provider already understands | Export a data pack from Studio using the existing format. |
| An event or operation already published by CHMOD | Register a typed ABI 2 callback from the shared DLL. Check allowed phases and modes in [hooks.json](../sdk/hooks.json). |
| An unpublished game function | Research it for the supported Xbox XEX. The current provider has an internal, exact-build binding path. A stable public hook requires the separate [runtime adapter workflow](../sdk/ADDING_HOOKS.md). |

For an internal binding, record the Xbox XEX hash, guest address, register
arguments and return values, caller and thread context, object lifetime, original
side effects, and evidence from Ghidra and the matching recompiled translation.
Confirm the target is distinct in the generated function map and the clean native
link map. Ghidra provides research evidence. The DLL resolves the guest address
through ReXGlue's function dispatcher at initialization.

## 2. Add and wire the feature

1. Add a feature source under `examples/scorebug_preview/` and list it in
   `add_library(scorebug_preview SHARED ...)` in the
   [CMake file](../examples/scorebug_preview/CMakeLists.txt). Follow
   [scorebug_elements.cpp](../examples/scorebug_preview/scorebug_elements.cpp)
   for an existing module. Keep one exported `ChmodQueryExtensionV2`, one
   extension descriptor, and one initialize/shutdown pair.
2. For a public hook, register it from `initialize` with `chmod::Host::add`
   and keep the returned registration token for cleanup. Use the typed payloads
   and accessors in [mod.hpp](../sdk/include/chmod/mod.hpp), and use the
   [minimal extension](../sdk/examples/minimal/extension.cpp) for the observe,
   transform, and replacement patterns. Declare the required capability and any
   exclusive replacement claim in the extension's launch configuration or
   package manifest. The [authoring guide](../sdk/AUTHORING.md) explains these fields.
3. For an internal hook, give the module a bind function that takes
   `rex::runtime::FunctionDispatcher&`. Call it from the provider's existing
   initialization chain, before queued hooks are enabled. Use
   `scorebug::hook(dispatcher, address, callback, original)` for interception
   and `scorebug::bind` for a game function the module only calls. The former
   records the target for the provider's centralized cleanup and provides the
   trampoline. Preserve original register and call behavior on the disabled
   and unsupported paths. The provider checks the executable hash before binding.
4. Validate feature settings before activation. Make absent settings or a
   disabled feature use stock behavior. Read project data from the staged
   overlay and put persistent player choices in the active user-data profile.
   For save-affecting features, document when settings take effect and what
   happens when an existing save is reopened with different settings.
5. Route partial initialization failures through cleanup. Unregister acquired
   public hook tokens, disable/remove installed internal hooks through the
   existing shutdown path, and release feature-owned state. Keep optional
   dependencies scoped to the feature that uses them. The current preview's
   overlay marker is a scorebug prerequisite and should be scoped to that
   feature before the shared provider supports standalone modules.

## 3. Build and prepare a test launch

From the repository root, set the PowerShell variables below to paths for the
same clean runtime build. Use the matching ReXGlue SDK, generated headers, and
native link map. The link map defaults to the executable path plus `.map`.

```powershell
cmake -S examples/scorebug_preview -B out/scorebug-dll -G Ninja `
  "-DCMAKE_PREFIX_PATH=$rexSdk" `
  "-DSCOREBUG_EXECUTABLE=$cleanExe" `
  "-DSCOREBUG_GENERATED_DIR=$generatedHeaders"
cmake --build out/scorebug-dll --target scorebug_preview
$providerDll = (Resolve-Path out/scorebug-dll/scorebug-preview.dll).Path
```

The CMake target embeds the clean executable hash. For the current scorebug
provider, use a generated D3D12 scorebug overlay and a saved launch JSON for
the same mod selection. Prepare and inspect the separate launch configuration
with native code explicitly authorized.

```powershell
pwsh -File tools/scorebugs/Launch-ScorebugPreview.ps1 `
  -OverlayRoot $overlay -ProviderDll $providerDll -Executable $cleanExe `
  -LaunchSettings $savedLaunch -AllowNativeCode -PrepareOnly
```

`-PrepareOnly` stages the DLL and reports the configuration without starting
the game. The preview script currently declares only
`lifecycle.runtime.ready`. If a feature uses another public hook, update the
declared capabilities and replacement claims used for its launch and release.

## 4. Check and submit

- Confirm the manifest and staged configuration agree on ABI, capabilities,
  replacement claims, DLL path, and SHA-256. Verify the vanilla executable and
  asset files are unchanged after staging.
- Test disabled and invalid settings, unsupported executable hashes, partial
  bind failure, and conflicts with another extension that claims the same hook.
  Check that the original behavior still works when the DLL is disabled.
- In a separate gameplay pass, verify the specific feature and any save/reload
  behavior in an isolated profile. Record build, preparation, and gameplay
  results separately.
- Submit feature source, its build entry, settings or schema changes, and
  verification notes for review. Keep local game files and test builds out of Git.
  Ship the rebuilt project DLL through the native-extension loader, with mod
  artwork and settings in the overlay.
