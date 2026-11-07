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
