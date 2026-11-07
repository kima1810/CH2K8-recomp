# ZMO beta 1 compatibility testing

The target is Windows 10/11 x64 on Intel/AMD CPUs with SSE4.1 and a D3D12-capable GPU/driver. ARM, 32-bit Windows, Linux and macOS are outside this binary beta. Passing setup checks is not proof that gameplay works. GPU memory, performance, controllers and mode-specific behavior require real hardware tests.

## Run each machine independently

1. Extract the full ZIP into a writable local folder. Do not copy DLLs or Python from another installation. Keep the version metadata and SHA256SUMS.txt.
2. Use your own original USA Xbox 360 ISO. Import ISO checks the supported default.xex identity, archive extents and minimum free space before extracting. It creates loose resources; the ISO is not mounted at play time. Decoded resources can use more space than the ISO. Do not import into cloud-synced folders for baseline testing.
3. Click Check setup. Start with D3D12 / Automatic / 720p / 60 Hz / Windowed. Run a cold launch, then a second launch to distinguish shader compilation from ongoing performance.
4. Test menu navigation, exhibition tip-off and several possessions, pause/unpause, replay/camera switches, controller unplug/reconnect, save, close, relaunch and reload. Test Legacy separately; it is not certified by the exhibition checks.
5. Change one setting at a time: native vs Accurate, borderless/exclusive, resolution, refresh, GPU adapter/driver, controller. Vulkan is experimental and applies only to ordinary extracted-disc installations, not imported loose assets.
6. Click Export bug report after a failure. It includes version, binary hashes, OS/CPU/GPU/driver information when available, selected launch options, preflight failures and bounded tails of the three latest runtime text logs and two latest ISO import logs. It does not include game data or saves. Common local paths are redacted; inspect the ZIP before posting. Add reproduction steps, expected/actual behavior, controller model, scene and the time of the failure. For a launcher startup failure check `%TEMP%/CH2K8-launcher-startup.log`.

## Compatibility record

Monitor refresh and guest timing are separate: a 120/144 Hz display retains
60 Hz guest video/VBlank timing. Automatic D3D12 GPU selection prefers Windows'
high-performance adapter; `--d3d12_adapter=N` keeps explicit DXGI index selection.
If a report still selects Intel UHD, confirm whether the machine has a discrete
GPU. Integrated-only systems may remain GPU limited at 720p. Include the full
exported report and frame timings; a startup log alone cannot establish FPS.

Use one row per configuration; leave untested cells as **untested**, never passed.

| Test ID | ZIP revision / runtime hash | Windows build | CPU / RAM | GPU / VRAM / driver | Display / scaling | Controller | Renderer / render path / mode / Hz | ISO import | Cold / warm boot | Menu / exhibition / replay | Save / reload | Legacy | Report / result |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Example | beta-version.json | build number | model / GiB | model / GiB / version | resolution / DPI | model | D3D12 / Automatic / windowed / 60 | untested | untested | untested | untested | untested | untested |

Prioritize AMD, NVIDIA and Intel GPUs; integrated and discrete adapters; Windows 10 and 11; older SSE4.1 CPUs and modern CPUs; clean PCs without Python/Visual Studio; spaces and non-ASCII folder names; 100%, 150% and 200% display scaling; standard accounts; and multiple controller types. Record unsupported systems as unsupported instead of filing an unexplained launch failure.

Command-line checks from the extracted beta folder:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/launch_ch2k8.ps1 -CheckSetup -GameData "C:/Games/CH2K8-assets"
powershell -NoProfile -ExecutionPolicy Bypass -File tools/launch_ch2k8.ps1 -ReportOutput "C:/Reports/CH2K8-unique-report.zip" -GameData "C:/Games/CH2K8-assets"
.\ch2k8_tools.exe inspect "C:/Games/CH2K8.iso"
powershell -NoProfile -ExecutionPolicy Bypass -File tools/verify_beta.ps1 -Root .
```

CheckSetup returns JSON and exit code 1 for failed preflight. ReportOutput still writes the report when preflight fails, then returns 1. Existing report files and installation destinations are not overwritten. No report is uploaded automatically.
