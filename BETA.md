# College Hoops 2K8 — ZMO beta 1

Download the **runnable Windows ZIP under Assets** from [the beta release](https://github.com/kima1810/CH2K8-decomp/releases/tag/ZMO-beta1-20261106). GitHub's automatic **Source code (zip)** is a developer checkout; it contains no `ch2k8.exe` and cannot launch until compiled.

## Install and play (Windows x64)

1. Extract the entire beta ZIP into a folder you can write to, such as Documents/CH2K8. Avoid Program Files. Keep the executable, DLLs and tools together.
2. Supply your own USA Xbox 360 game data. No game files are included in the beta download.
3. Double-click **Launch CH2K8.cmd**. For an ISO, click **Import ISO...**, select the ISO, then choose a parent folder for the new installation. The launcher creates `<ISO name>-assets`, extracts editable loose resources, and selects it when finished. Allow several minutes and enough free space for decoded assets. Progress and cancellation are available; the original ISO is unchanged. Existing destinations are never overwritten. Later launches reuse the extracted folder. If you already have a game folder containing `default.xex`, use **Browse...** instead. Click **Check setup**, then **Launch game**.
4. Start with Direct3D 12, Automatic, 1280x720, 60 Hz, Windowed. Increase resolution or choose borderless after checking gameplay. Accurate Xbox blending is the slower compatibility option. Vulkan remains experimental; folder asset replacements require D3D12.

The complete beta ZIP includes standalone native asset tools, required Microsoft C++ runtime DLLs, and pinned SDL controller mappings. The launcher, ISO importer, asset preparation and package verifier do not ship or invoke Python. Testers do not need to install Python, Visual Studio, a compiler or SDK, and no download is needed at first launch. Folder edits are validated/prepared before launch. The binary target is Windows 10/11 x64 on Intel/AMD CPUs with SSE4.1 and a D3D12-capable GPU/driver; ARM, 32-bit Windows, Linux and macOS are outside this beta. The importer checks the original USA executable hash, archive part extents and minimum free space before extracting. Other games/revisions are refused. Decoded assets can require more than the initial space estimate. The ISO is converted into the loose folder system, rather than mounted directly. Failed or cancelled imports discard their temporary extraction and leave existing installations untouched. Import logs are saved in `port/userdata/imports`.

Command-line import is also available from the beta folder:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/launch_ch2k8.ps1 -ImportIso "D:\Games\College Hoops 2K8.iso" -InstallDirectory "D:\Games\CH2K8-assets"
```

Add `-Launch` to start the game after a successful import. You can also use `ch2k8_tools.exe import "PATH/TO/GAME.iso" "PATH/TO/NEW FOLDER"`; existing destinations are refused.

Settings and saves stay in `port/userdata` beside the launcher. **Saves / settings** opens that folder; back it up before updating. Extract updates to a new folder, then copy your userdata into the same location. Keep game data separately and select it again. Remove the beta folder to uninstall after backing up saves; your separately stored game data remains available.

First startup can take longer while shaders compile. If launch fails, use **Check setup** and confirm the complete ZIP was extracted. **Open logs** opens the selected runtime's logs folder. Click **Export bug report** to create a ZIP with version and runtime hashes, hardware/driver information, selected options, preflight results and recent log tails. Common paths are redacted, but review the ZIP before sharing and add reproduction steps. See **BETA_TESTING.md** for the cross-PC test matrix. No report is uploaded automatically. Exit the game before changing runtime files.

## Beta scope

This is an experimental native recompilation. Menu boot and live gameplay have been observed; full-game completion and Legacy are untested. Direct folder resources, growing rosters, native audio replacement and additional texture layouts still need manual in-game acceptance. See `port/README.md` and `docs/formats/loose_assets.md` in the source repository for evidence and limits.

## Build the distributable (maintainers)

Build the current patched dual-backend runtime using `port/README.md`, then run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/prepare_beta_deps.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File tools/package_beta.ps1
```

The script creates a new timestamped portable ZIP under `out/beta`, containing the executable, required runtime DLLs, launcher, asset preparation tools, version metadata, third-party notices and a SHA-256 inventory. Dependency preparation pins the SDL controller database and license by SHA-256 and copies redistributable x64 CRT DLLs from Visual Studio; pass `-CrtDirectory` if it is installed elsewhere. Packaging fails if these dependencies are missing. It includes no disc data, generated source, saves or developer environment. The source branch does not contain compiled binaries; distribute the ZIP separately after beta acceptance testing. Building from source still requires the SDK and game data described in `port/README.md`.

The native tool is built with `cmake --build port/out/build/win-amd64-vulkan --target ch2k8_tools`. Python remains part of the source code-generation/research toolchain and automated developer tests; it is not needed by the distributed launcher.

To build only the launcher asset executable without the game SDK, game data or Python:

```powershell
cmake -S tools/native_assets -B out/native-tools -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build out/native-tools --parallel 3
```

## Build from your XEX or ISO (source checkout)

Open the source checkout's launcher and click **Build from XEX / ISO**, or run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/build_ch2k8.ps1 -Source "C:/Games/CH2K8/default.xex"
powershell -NoProfile -ExecutionPolicy Bypass -File tools/build_ch2k8.ps1 -Source "C:/Games/CH2K8.iso"
```

This builds the native helper, validates the supported USA XEX, stages a private code-generation input, prepares the pinned SDK when missing, generates the recompilation and builds `ch2k8.exe`. ISO builds also import editable disc assets. A standalone XEX supplies executable code; playing still requires the disc assets. Use **Select XEX...** for an already extracted disc with `default.xex` and archive parts beside it, or **Import ISO...** for the complete disc image.

Source builds require Python 3.11+, Git, CMake 3.25+, Ninja, Clang 20+ and Microsoft C++ Build Tools with the Windows SDK. The resolver probes real interpreters, the `py -3` launcher, Python's registry installation entries and standard installation folders, skipping Windows Store execution aliases. If Python is installed somewhere else, pass `-PythonExecutable "C:/path/to/python.exe"`. `-ValidateOnly` reports the selected prerequisites without building; `-SdkDirectory` reuses a patched installed SDK; `-CodeOnly` skips ISO asset import for code-generation testing. Keep a minimum of several GB free on the build drive. First SDK/game builds can take 30 minutes or longer. UI build logs are under `port/userdata/builds`.

The source build writes `port/userdata/build-result.json` and remembers the executable and game-data path for the next launcher session. The runnable release asset continues to use native tools and does not require Python, compilers, Git or an SDK.

## Source-build diagnostics update

See [BUILDING.md](https://github.com/kima1810/CH2K8-decomp/blob/ZMO-beta1/BUILDING.md) for the current ISO-to-executable workflow. The source builder imports the Visual Studio x64 environment automatically, detects bundled tools, records prerequisite failures before compilation, streams both native output channels, and reports failed stage/exit code/recovery advice. Use `-InstallDirectory` to place ISO assets on a different drive and `-Jobs 1` when memory is limited. A different XEX hash is a revision-compatibility report, not evidence of an illegitimate copy.
