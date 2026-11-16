<# Verify a pristine beta folder without any external runtime or interpreter. #>
[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$Root)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSHOME 'Modules/Microsoft.PowerShell.Utility')
$Root = (Resolve-Path -LiteralPath $Root).Path
. (Join-Path $PSScriptRoot 'pe_imports.ps1')
$listed = @{}
foreach ($line in [IO.File]::ReadAllLines((Join-Path $Root 'SHA256SUMS.txt'))) {
    $pair = $line -split '  ',2
    if ($pair.Length -ne 2 -or $pair[0] -notmatch '^[0-9a-f]{64}$') { throw 'Invalid inventory line' }
    $file = [IO.Path]::GetFullPath((Join-Path $Root $pair[1]))
    if (-not $file.StartsWith($Root + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Inventory escapes package' }
    if ($listed.ContainsKey($file)) { throw 'Duplicate inventory path' }
    $listed[$file] = $true
    if ((Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant() -ne $pair[0]) { throw "Checksum mismatch: $($pair[1])" }
}
foreach ($name in @('ch2k8.exe','rexruntime.dll','rexgpu-xenos.dll','ch2k8_tools.exe','tools/launch_ch2k8.ps1','tools/beta_diagnostics.ps1','gamecontrollerdb.txt')) {
    if (-not (Test-Path -LiteralPath (Join-Path $Root $name) -PathType Leaf)) { throw "Missing beta component: $name" }
}
$system = 'advapi32 bcrypt cfgmgr32 combase comdlg32 crypt32 cryptbase dbgcore dbghelp d3d12 d3dcompiler_47 dxgi dwmapi gdi32 imm32 iphlpapi kernel32 kernelbase mswsock ncrypt normaliz ntdll ole32 oleaut32 powrprof psapi propsys rpcrt4 sechost secur32 setupapi shell32 shlwapi shcore user32 userenv uxtheme version winhttp wininet winmm wintrust ws2_32 wtsapi32 ucrtbase' -split ' '
$binaries = @()
foreach ($item in Get-ChildItem -LiteralPath $Root -File -Recurse) {
    if ($item.Name -ne 'SHA256SUMS.txt' -and -not $listed.ContainsKey($item.FullName)) { throw "Unlisted package file: $($item.Name)" }
    $relative=$item.FullName.Substring($Root.Length+1).Replace('\','/')
    if ($item.Extension -in @('.pyc','.pyd') -or ($item.Extension -eq '.py' -and -not $relative.StartsWith('sdk/')) -or $item.Name -match '(?i)python') { throw "Interpreter dependency must not enter beta: $($item.Name)" }
    if ($item.Extension -notin @('.exe','.dll')) { continue }
    $imports = @(Get-PeImports $item.FullName)
    $local = @(Get-ChildItem -LiteralPath $item.DirectoryName -File | ForEach-Object { $_.Name.ToLowerInvariant() })
    foreach ($dll in $imports) {
        if ($dll -in $local -or $dll -match '^(api-ms-win-|ext-ms-win-)' -or ($dll -replace '\.dll$','') -in $system) { continue }
        throw "Unbundled dependency: $($item.Name) -> $dll"
    }
    $binaries += @{path=$item.FullName.Substring($Root.Length+1);imports=$imports}
}
@{verified=$true;files=$listed.Count;binaries=$binaries} | ConvertTo-Json -Depth 5
