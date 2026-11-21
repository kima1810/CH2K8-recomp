# Scorebug DLL

The ESPN and USA Sports scorebugs use two pieces. The CHMOD ABI 2 DLL applies in-memory hooks to the tested ZMO-beta1 runtime, and the generated asset overlay supplies the two converted scenes. The game executable and original asset root stay untouched.

Build against the ReXGlue SDK and generated headers used for the target runtime. The DLL is bound to the SHA-256 of that exact executable because the hooks use the retail guest function addresses and layout.

```powershell
cmake -S examples/scorebug_preview -B out/scorebug-dll -G Ninja `
  "-DCMAKE_PREFIX_PATH=$rexSdk" `
  "-DSCOREBUG_EXECUTABLE=$cleanExe" `
  "-DSCOREBUG_GENERATED_DIR=$generatedHeaders"
cmake --build out/scorebug-dll
```

The target link map defaults to the executable path with `.map` appended. CMake rejects a link map containing the old compiled-in prototype. MinHook is pinned and linked into the DLL.

Prepare the D3D12 offset-preserving preview overlay with the converted scenes and the asset cache for the selected mods. Keep the saved launch settings and their original CHMOD configuration available. The launch script stages the DLL through the existing CHMOD ABI 2 loader and preserves the selected extensions and save profile.

```powershell
pwsh -File tools/scorebugs/Launch-ScorebugPreview.ps1 `
  -OverlayRoot $overlay -ProviderDll $scorebugDll -Executable $cleanExe `
  -LaunchSettings $savedLaunch -Style ESPN -AllowNativeCode -PrepareOnly
```

Remove `-PrepareOnly` to start the game. Use `-Style` to override the saved style for that launch. The Scorebug item becomes available after reopening Presentation and changes the style on the next match load. Its selection is saved in the active user profile.

## Match-rule prototype

The settings below describe the local research build. Support for them requires
the separate match-rule implementation and gameplay verification.

Place `chmod-match-rules.json` in the active user profile, the path passed as `--user_data_root`:

```json
{"version": 1, "shot_clock_seconds": 30, "three_point_distance_inches": 265.75}
```

The DLL reads the rules once during startup. Omit either field to keep that rule stock, or remove the file to disable both overrides.

- `shot_clock_seconds` accepts whole seconds from 1 through 99. It replaces the standard 35-second duration at initialization, including the stock reset values. Offensive rebounds still use the native reset policy. See the [shot-clock findings](../../docs/findings/2026-11-21-match-rule-clock.md).
- `three_point_distance_inches` accepts 1 through 300 inches, including fractions. It sets both the arc radius and the straight corner offset to the same distance. On narrow courts the DLL limits the line to two feet inside each sideline. The scoring boundary changes in memory. Court paint comes from the arena's artwork and needs a matching overlay. See the [three-point findings](../../docs/findings/2026-11-21-three-point-distance.md).
