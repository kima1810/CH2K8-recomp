# College Hoops 2K8 native recompilation beta

[Download the runnable Windows x64 beta](https://github.com/kima1810/CH2K8-decomp/releases/tag/ZMO-beta1-20261106). Choose the **CH2K8-ZMO-beta1-Windows-x64-*.zip** file under **Assets**. GitHub's automatic source archives contain developer files and require compilation.

Extract the full runnable ZIP, open **Launch CH2K8.cmd**, then **Import ISO...** or **Select XEX...** from your extracted USA Xbox 360 disc. The runnable beta includes `ch2k8.exe`, runtime DLLs and native asset tools; it requires no Python or compiler. Supply your own game data. A bare XEX contains code and still needs the disc assets for playing.

The source checkout's launcher offers **Build from XEX / ISO**. Source compilation requires Python 3.11+, Git, CMake, Ninja, Clang and Microsoft C++ Build Tools plus the Windows SDK. The build script detects real Python installations and skips Store execution aliases:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/build_ch2k8.ps1 -Source "C:/Games/College Hoops 2K8.iso"
# Or supply the original USA XEX, with disc assets available separately:
powershell -NoProfile -ExecutionPolicy Bypass -File tools/build_ch2k8.ps1 -Source "C:/Games/CH2K8/default.xex"
```

Use `-PythonExecutable "C:/path/to/python.exe"` when needed, and `-ValidateOnly` to check the selected prerequisites. See [installation and building](BETA.md), [developer build details](port/README.md), and the [multi-PC beta test checklist](BETA_TESTING.md).

This is a beta targeting Windows 10/11 x64, Intel/AMD SSE4.1 CPUs and compatible graphics drivers. Full-game completion, Legacy, edited assets and additional hardware still need tester coverage. Use **Export bug report** after a failure and include reproduction steps.

For the complete ISO-to-executable workflow, prerequisites, stage-by-stage recovery and compatibility limits, see [BUILDING.md](BUILDING.md). Builds automatically load the Microsoft x64 compiler environment and always save a structured failure report.

## Crash reports on Windows

The launcher writes a timestamped runtime log to the `logs` directory next to
the game executable. On an unhandled Windows exception or CRT abort, the game
attempts to write a same-named `.dmp` with native thread and module information.
Open it in WinDbg with symbols from the matching build. Use **Export bug report**
for runtime logs, build information, and renderer settings. Add steps to
reproduce and attach the dump separately after reviewing it for process memory
you may wish to keep private.

With the patched source SDK, an invalid indirect guest call also logs the guest
target, link register (caller return address), count register, and stack pointer.
Look up the guest target and return address in the matching Xbox executable in
Ghidra. A forced process kill or a fault before reporter initialization can leave
only a partial runtime log.

The reusable [C++ extension SDK](sdk/README.md) is hosted with
[Modding Studio](https://github.com/ZMO34/CHoops-Extractor-Reborn-Recomp/tree/feat/chmod-extension-sdk/sdk),
with [draft integration PR #3](https://github.com/ZMO34/CHoops-Extractor-Reborn-Recomp/pull/3).
See [CHMOD API1.3](docs/formats/chmod-1.3.md) for ABI2 native extensions and
[the implementation report](docs/findings/2026-11-08-extension-framework.md).
Current framework/adapters/examples are compiled; runtime tests and gameplay
verification remain pending. Native code requires explicit launcher opt-in.

The launcher now includes **Update from GitHub** and **Rollback update**.
See [runtime update documentation](docs/RUNTIME_UPDATES.md) for safe installation,
release requirements and verification limits. The currently published older beta
cannot downgrade the local SDK runtime. Tests/game execution remain user-run.

## Modding and research

Start with the [folder modding guide](docs/MODDING.md) and
[editor export contract](docs/formats/mod-folder-editor.md).
The [recent ZMO research index](docs/research/zmo-beta-research.md) links the
asset, court, uniform, native-hook, scorebug and portability findings, with
remaining verification work recorded for each feature.
