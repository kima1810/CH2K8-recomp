# Shared beta preflight and privacy-conscious tester report export.
function Initialize-BetaNative {
if (-not ('Ch2k8BetaNative' -as [type])) {
    Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public static class Ch2k8BetaNative {
 [DllImport("kernel32.dll", SetLastError=true, CharSet=CharSet.Unicode)] public static extern IntPtr LoadLibraryEx(string path, IntPtr file, uint flags);
 [DllImport("kernel32.dll")] public static extern bool FreeLibrary(IntPtr module);
 [DllImport("kernel32.dll")] public static extern bool IsProcessorFeaturePresent(uint feature);
 [DllImport("d3d12.dll")] public static extern int D3D12CreateDevice(IntPtr adapter, uint level, ref Guid iid, out IntPtr device);
}
"@
}
}
function Test-BetaEnvironment {
    param($Configuration)
    Initialize-BetaNative
    $failures = New-Object 'System.Collections.Generic.List[string]'
    $warnings = New-Object 'System.Collections.Generic.List[string]'
    $binaryRoot = Split-Path -Parent $Configuration.executable
    if (-not [Environment]::Is64BitProcess -or $env:PROCESSOR_ARCHITECTURE -ne 'AMD64') { $failures.Add('Use Windows x64 on an Intel/AMD PC. ARM and 32-bit hosts are not supported by this beta.') }
    if ([Environment]::OSVersion.Version.Major -lt 10) { $failures.Add('Windows 10 or 11 x64 is required.') }
    if (-not [Ch2k8BetaNative]::IsProcessorFeaturePresent(37)) { $failures.Add('The CPU must support SSE4.1.') }
    if (-not (Test-Path -LiteralPath $Configuration.executable -PathType Leaf)) { $failures.Add('Game executable missing. Extract the complete beta ZIP.') }
    foreach ($name in @('rexruntime.dll', 'rexgpu-xenos.dll')) {
        $path = Join-Path $binaryRoot $name
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { $failures.Add("Missing $name. Extract the complete beta ZIP."); continue }
        $handle = [Ch2k8BetaNative]::LoadLibraryEx($path, [IntPtr]::Zero, 0x1100)
        if ($handle -eq [IntPtr]::Zero) { $failures.Add("Unable to load $name (Windows error $([Runtime.InteropServices.Marshal]::GetLastWin32Error())). Extract all runtime DLLs; check Windows/GPU updates.") }
        else { $null = [Ch2k8BetaNative]::FreeLibrary($handle) }
    }
    $dataArgument = $Configuration.arguments | Where-Object { $_.StartsWith('--game_data_root=') }
    $data = $dataArgument.Substring('--game_data_root='.Length)
    $xexHash = $null
    if (Test-Path -LiteralPath (Join-Path $data 'default.xex') -PathType Leaf) { $xexHash = (Get-FileHash -LiteralPath (Join-Path $data 'default.xex') -Algorithm SHA256).Hash.ToLowerInvariant() }
    if (-not $xexHash) { $failures.Add('Choose a game folder containing default.xex, or use Import ISO.') }
    elseif ($xexHash -ne '71e8983d1cc009e485696aad19b5fa4b4661761870e2c8972717b932c1e4be36') { $failures.Add('Unsupported default.xex. This beta requires the original USA Xbox 360 College Hoops 2K8 executable; other games/revisions are not compatible.') }
    if (Test-Path -LiteralPath (Join-Path $data 'assets.json')) {
        foreach ($name in @('assets.map', 'native_dds.index', 'assets')) {
            if (-not (Test-Path -LiteralPath (Join-Path $data $name))) { $failures.Add("Incomplete imported installation: $name. Import the ISO into a new folder.") }
        }
        if ($Configuration.arguments -contains '--ch2k8_renderer=vulkan') { $failures.Add('Imported folder assets require Direct3D 12.') }
        try {
            $assetTool = Get-AssetTool
            $probeOutput = & $assetTool version 2>&1
            if ($LASTEXITCODE -ne 0) { throw 'Native asset tools could not start. Extract the complete beta ZIP.' }
        } catch { $failures.Add("Asset tools unavailable: $($_.Exception.Message)") }
    }
    if ($xexHash -and -not (Test-Path -LiteralPath (Join-Path $data 'assets.json'))) {
        foreach ($letter in [char[]]'ABCDEFGHIJKLM') {
            if (-not (Test-Path -LiteralPath (Join-Path $data ('0' + $letter)) -PathType Leaf)) { $failures.Add("Extracted disc is missing archive part 0$letter. Use a complete disc extraction or Import ISO."); break }
        }
    }
    foreach ($folder in @((Join-Path $repoRoot 'port/userdata'), (Join-Path $binaryRoot 'logs'))) {
        $probe = Join-Path $folder ('.beta-write-' + [guid]::NewGuid().ToString('N'))
        try {
            $null = New-Item -ItemType Directory -Path $folder -Force
            [IO.File]::WriteAllText($probe, 'test')
        } catch { $failures.Add('The beta folder must be writable. Extract it into Documents or another user-owned folder.') }
        finally { if (Test-Path -LiteralPath $probe -PathType Leaf) { Remove-Item -LiteralPath $probe } }
    }
    if ($Configuration.arguments -contains '--ch2k8_renderer=d3d12') {
        try {
            $device = [IntPtr]::Zero
            $iid = [guid]'189819f1-1db6-4b57-be54-1821339b85f7'
            $hr = [Ch2k8BetaNative]::D3D12CreateDevice([IntPtr]::Zero, 0xb000, [ref]$iid, [ref]$device)
            if ($hr -lt 0) { $failures.Add('Direct3D 12 device creation failed. Install the GPU vendor driver and check D3D12 support.') }
            if ($device -ne [IntPtr]::Zero) { $null = [Runtime.InteropServices.Marshal]::Release($device) }
        } catch { $failures.Add("Direct3D 12 is unavailable: $($_.Exception.Message)") }
    } else {
        $handle = [Ch2k8BetaNative]::LoadLibraryEx('vulkan-1.dll', [IntPtr]::Zero, 0x1000)
        if ($handle -eq [IntPtr]::Zero) { $failures.Add('Vulkan loader is missing. Install a Vulkan-capable GPU driver.') }
        else { $null = [Ch2k8BetaNative]::FreeLibrary($handle) }
        $warnings.Add('Vulkan GPU features and rendering remain experimental; loader detection alone does not establish compatibility.')
    }
    $warnings.Add('Preflight does not establish gameplay correctness or performance on this GPU.')
    [pscustomobject]@{ ready = ($failures.Count -eq 0); failures = @($failures.ToArray()); warnings = @($warnings.ToArray()); xex_sha256 = $xexHash }
}
function Read-BetaLogTail([string]$Path) {
    $stream = [IO.File]::Open($Path, 'Open', 'Read', 'ReadWrite')
    try {
        $null = $stream.Seek([Math]::Max(0, $stream.Length - 262144), 'Begin')
        $reader = New-Object IO.StreamReader($stream)
        try { return $reader.ReadToEnd() } finally { $reader.Dispose() }
    } finally { $stream.Dispose() }
}
function Export-BetaReport {
    param([string]$Destination, $Configuration, $Setup, [string]$Notes = '')
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    if (-not $Destination) { throw 'Choose a report ZIP destination.' }
    $Destination = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Destination)
    if (Test-Path -LiteralPath $Destination) { throw 'Report already exists. Choose a new filename.' }
    $reports = Join-Path $repoRoot 'port/userdata/reports'
    $stage = Join-Path $reports ([guid]::NewGuid().ToString('N'))
    $null = New-Item -ItemType Directory -Path $stage -Force
    $dataArgument = $Configuration.arguments | Where-Object { $_.StartsWith('--game_data_root=') }
    $data = $dataArgument.Substring('--game_data_root='.Length)
    function Protect-BetaText([string]$Value) {
        foreach ($pair in @(@($data, '<GAME>'), @($repoRoot, '<BETA>'), @($env:USERPROFILE, '<USER>'))) {
            if ($pair[0]) { $Value = $Value.Replace([string]$pair[0], [string]$pair[1]).Replace(([string]$pair[0]).Replace('\','/'), [string]$pair[1]) }
        }
        return $Value
    }
    try { Import-Module (Join-Path $PSHOME 'Modules/CimCmdlets') } catch { }
    $hardware = @{}
    foreach ($item in @(@('os', 'Win32_OperatingSystem', @('Caption','Version','BuildNumber','OSArchitecture','TotalVisibleMemorySize')), @('cpu', 'Win32_Processor', @('Name','NumberOfCores','NumberOfLogicalProcessors')), @('gpu', 'Win32_VideoController', @('Name','DriverVersion','DriverDate','CurrentHorizontalResolution','CurrentVerticalResolution')))) {
        try { $hardware[$item[0]] = @(Get-CimInstance -ClassName $item[1] -OperationTimeoutSec 5 | Select-Object -Property $item[2]) }
        catch { $hardware[$item[0]] = 'unavailable' }
    }
    # Registry fallback also works where WMI/CIM is disabled by policy.
    if ($hardware.os -eq 'unavailable') {
        try {
            $os = Get-ItemProperty 'HKLM:/SOFTWARE/Microsoft/Windows NT/CurrentVersion'
            $hardware.os = @{name=$os.ProductName;build=$os.CurrentBuildNumber;revision=$os.UBR;display_version=$os.DisplayVersion;source='registry'}
        } catch { }
    }
    if ($hardware.cpu -eq 'unavailable') {
        try { $hardware.cpu = @{name=(Get-ItemProperty 'HKLM:/HARDWARE/DESCRIPTION/System/CentralProcessor/0').ProcessorNameString;logical_processors=[Environment]::ProcessorCount;source='registry'} } catch { }
    }
    if ($hardware.gpu -eq 'unavailable') {
        try {
            $hardware.gpu = @(Get-ChildItem 'HKLM:/SYSTEM/CurrentControlSet/Control/Class/{4d36e968-e325-11ce-bfc1-08002be10318}' | ForEach-Object {
                $adapter = Get-ItemProperty -LiteralPath $_.PSPath -ErrorAction SilentlyContinue
                if ($adapter.DriverDesc) { @{name=$adapter.DriverDesc;driver_version=$adapter.DriverVersion;driver_date=$adapter.DriverDate;source='registry'} }
            })
        } catch { }
    }
    $version = @{}
    $versionFile = Join-Path $repoRoot 'beta-version.json'
    if (Test-Path -LiteralPath $versionFile) { $version = Get-Content -LiteralPath $versionFile -Raw | ConvertFrom-Json }
    $hashes = @{}
    foreach ($name in @('ch2k8.exe', 'rexruntime.dll', 'rexgpu-xenos.dll', 'ch2k8_tools.exe')) {
        $file = Join-Path (Split-Path -Parent $Configuration.executable) $name
        if (Test-Path -LiteralPath $file) { $hashes[$name] = (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant() }
    }
    $lastLaunch = $null
    $lastLaunchPath = Join-Path $repoRoot 'port/userdata/last-launch.json'
    if (Test-Path -LiteralPath $lastLaunchPath) {
        try { $lastLaunch = Get-Content -LiteralPath $lastLaunchPath -Raw | ConvertFrom-Json } catch { }
    }
    $report = @{ last_launch=$lastLaunch; format=1; captured_utc=[DateTime]::UtcNow.ToString('o'); version=$version; hardware=$hardware; runtime_sha256=$hashes; setup=$Setup; arguments=$Configuration.arguments; notes=$Notes }
    Protect-BetaText ($report | ConvertTo-Json -Depth 8) | Set-Content -LiteralPath (Join-Path $stage 'report.json') -Encoding UTF8
    'Describe what happened, expected behavior, steps to reproduce, game mode, controller and approximate session time. Attach a screenshot if useful. Review this ZIP before sharing: logs and notes can contain personal paths. No game data or saves are included.' | Set-Content -LiteralPath (Join-Path $stage 'READ ME.txt') -Encoding UTF8
    # Include only a bounded tail of the three latest runtime text logs.
    $logs = Join-Path (Split-Path -Parent $Configuration.executable) 'logs'
    if (Test-Path -LiteralPath $logs) {
        $index = 0
        Get-ChildItem -LiteralPath $logs -File | Where-Object { $_.Extension -in @('.log','.txt') } | Sort-Object LastWriteTime -Descending | Select-Object -First 3 | ForEach-Object {
            $index++
            $tail = Read-BetaLogTail $_.FullName
            Protect-BetaText $tail | Set-Content -LiteralPath (Join-Path $stage "runtime-$index.log") -Encoding UTF8
        }
    }
    $imports = Join-Path $repoRoot 'port/userdata/imports'
    if (Test-Path -LiteralPath $imports) {
        $index = 0
        Get-ChildItem -LiteralPath $imports -Directory | Sort-Object LastWriteTime -Descending | Select-Object -First 2 | ForEach-Object {
            $path = Join-Path $_.FullName 'import.log'
            if (Test-Path -LiteralPath $path -PathType Leaf) {
                $index++
                Protect-BetaText (Read-BetaLogTail $path) | Set-Content -LiteralPath (Join-Path $stage "import-$index.log") -Encoding UTF8
            }
        }
    }
    [IO.Compression.ZipFile]::CreateFromDirectory($stage, [IO.Path]::GetFullPath($Destination), [IO.Compression.CompressionLevel]::Optimal, $true)
    return [IO.Path]::GetFullPath($Destination)
}
