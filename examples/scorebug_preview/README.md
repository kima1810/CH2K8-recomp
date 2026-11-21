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
