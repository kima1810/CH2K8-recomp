# Build College Hoops 2K8 from your ISO

Use the current **ZMO-beta1 branch**, not an old source ZIP. Source archives contain no compiled game: **Import ISO** prepares assets, while **Build from XEX / ISO** generates and compiles the game. For playing without developer tools, download the runnable Windows ZIP from [release Assets](https://github.com/kima1810/CH2K8-decomp/releases/tag/ZMO-beta1-20261106).

## Windows development setup

Use Windows 10/11 x64 on Intel/AMD. Install:

- Visual Studio 2022/2026 Build Tools with **Desktop development with C++**, MSVC x64/x86 tools and a Windows 10/11 SDK.
- LLVM **Clang 20 or later**, CMake **3.25 or later**, Ninja and Git. CMake/Ninja/LLVM bundled with Visual Studio are detected when available; the LLVM version must still meet the minimum.
- Python **3.11 or later**. A real interpreter is detected via installed locations, registry and `py`; Microsoft Store aliases are skipped.

Keep source in a short local writable path, for example `C:/dev/CH2K8`. SDK downloads and compilation need several GB; decoded ISO assets can take substantially more than the disc image. Cloud-synced folders, network drives and Wine are not validated build environments. Do not build two processes in the same checkout. No administrator/developer terminal is required after the prerequisites are installed: the script imports the newest complete x64 Microsoft compiler environment automatically. A small Windows C++ program is compiled, linked and run during preflight, catching mixed STL/library and missing redistributable problems before the SDK build.

## One build command

From the source root, first check prerequisites:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/build_ch2k8.ps1 -Source "D:/Games/College Hoops 2K8.iso" -ValidateOnly
```

Then build (omit `-ValidateOnly`):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/build_ch2k8.ps1 -Source "D:/Games/College Hoops 2K8.iso" -InstallDirectory "D:/Games/CH2K8-assets" -Jobs 2
```

The launcher also has **Build from XEX / ISO**. The script builds the native importer, validates/extracts the executable, downloads the exact SDK and its pinned dependencies if absent, applies tracked patches, generates/corrects the recompilation, builds Release targets, imports assets and validates the map through the game reader. SDK source/build/install and generated code remain local. First builds can take 30 minutes or longer. Rerunning reuses downloads and compilation; existing disc/asset folders are not erased.

- `-CodeOnly` builds the executable without importing assets, useful for compiler testing or when assets are already installed.
- `-Jobs 1` reduces memory pressure on smaller PCs. Without an explicit setting, PCs with under 12 GB RAM use one compiler job; others default to two.
- `-PythonExecutable "C:/path/to/python.exe"` selects a particular interpreter.
- `-SdkDirectory "C:/path/to/installed-sdk"` reuses a complete patched SDK.
- `-BuildDirectory "C:/dev/builds/CH2K8-new"` starts a separate game CMake cache when moving source or changing compilers.
- `-InstallDirectory` chooses a new ISO asset destination, including a different drive. Its parent folder must exist. Existing compatible installations are prepared and validated again.
- `-LogFile "C:/dev/logs/ch2k8/build.log"` chooses the build report folder.

An extracted disc folder or original `default.xex` may be passed instead of an ISO. A bare XEX supplies code, not the assets needed for play.

## Failure reports and recovery

Every invocation creates `build.log` and `status.json` under `port/userdata/builds/<timestamp>`, including failures before compilation. A successful prerequisite check also writes `environment.json` with actual tool paths. Reports contain local paths; review them before sharing. The GUI shows the current stage and the final error/recovery text, rather than only a generic missing-executable message. During ISO installation, `asset-progress.json` records importer progress. Successful builds write `port/userdata/build-result.json`.

| Failed stage | Action |
| --- | --- |
| input / iso-executable | Confirm disc root, complete Xbox 360 ISO and reported executable hash. ZIP/7z, GOD/STFS and PS3 containers need their own extraction/conversion first. |
| prerequisites / compiler-probe / compiler-runtime | Install the missing component/version shown in the report; rerun from ordinary PowerShell. |
| sdk-clone / sdk-submodules | Check GitHub/proxy access and disk space, then rerun to resume. Git long-path handling is enabled for dependency checkout. |
| sdk-patches | Use the pinned SDK with current tracked scripts. Report unrecognized patch targets; do not bypass them. |
| sdk-configure / game-configure | Check the CMake error. Use a new game build directory for a stale/moved cache. Existing files are preserved. |
| sdk-build / game-build | Read the final compiler/linker error. Try `-Jobs 1` for memory exhaustion. |
| iso-assets / asset-prepare / runtime-map | The game may already be compiled. Check free space and import errors; choose a new asset destination or use `-CodeOnly` for compiler-only testing. |

Attach `status.json`, `environment.json` and `build.log` to a build bug report, with source revision, Windows version, reproduction command and observed XEX hash. Do not upload the ISO, XEX, extracted assets or generated game source.

## Compatibility and repository contents

The verified executable is the original USA Xbox 360 revision, SHA-256 `71e8983d1cc009e485696aad19b5fa4b4661761870e2c8972717b932c1e4be36`. The native reader accepts standard full/trimmed partition layouts and searches sector-aligned descriptors within the first 1 GiB for other layouts. Archive bounds, executable identity and resource formats are still validated. A hash mismatch does **not** mean a copy is illegitimate. Another executable revision needs separate code/layout validation; accepting its hash alone cannot make fixed-address generated code work.

GitHub contains the source, manifest/configuration, SDK patch scripts, native asset tools, launcher, build scripts, tests and notices. The SDK is fetched from the recorded pinned revision and submodule commits; an initial SDK build requires internet access. Retail disc contents and generated proprietary game code are intentionally absent. The separate runnable release contains the host executable, native helper, required runtime DLLs and controller mappings.

The supported runtime target remains Windows x64 with SSE4.1 and compatible graphics drivers. Other executable revisions, macOS/Linux/ARM/Wine and all GPU models are not certified by these checks. Use the beta hardware/gameplay test matrix to expand coverage.
