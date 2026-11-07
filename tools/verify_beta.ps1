<# Verify a pristine beta folder without any external runtime or interpreter. #>
[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$Root)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSHOME 'Modules/Microsoft.PowerShell.Utility')
$Root = (Resolve-Path -LiteralPath $Root).Path
function Get-PeImports([string]$File) {
    $data = [IO.File]::ReadAllBytes($File)
    if ($data.Length -lt 64 -or $data[0] -ne 77 -or $data[1] -ne 90) { throw "Invalid Windows binary: $File" }
    $pe = [BitConverter]::ToInt32($data, 60)
    if ($pe -lt 0 -or $pe + 24 -gt $data.Length -or [BitConverter]::ToUInt32($data, $pe) -ne 0x4550) { throw 'Invalid PE signature' }
    if ([BitConverter]::ToUInt16($data, $pe + 4) -ne 0x8664) { throw 'Non-x64 beta binary' }
    $count = [BitConverter]::ToUInt16($data, $pe + 6)
    $size = [BitConverter]::ToUInt16($data, $pe + 20)
    $optional = $pe + 24
    if ($optional + $size + $count * 40 -gt $data.Length -or [BitConverter]::ToUInt16($data, $optional) -ne 0x20b) { throw 'Invalid PE32+ headers' }
    $sections = @()
    for ($i=0; $i -lt $count; $i++) {
        $o = $optional + $size + $i * 40 + 8
        $sections += @{ virtual_size=[BitConverter]::ToUInt32($data,$o); address=[BitConverter]::ToUInt32($data,$o+4); raw_size=[BitConverter]::ToUInt32($data,$o+8); pointer=[BitConverter]::ToUInt32($data,$o+12) }
    }
    function Resolve-PeRva([uint32]$Value) {
        foreach ($s in $sections) {
            if ($Value -ge $s.address -and $Value -lt $s.address + [Math]::Max($s.virtual_size,$s.raw_size)) {
                $offset = [long]$s.pointer + $Value - $s.address
                if ($offset -lt 0 -or $offset -ge $data.Length) { throw 'Invalid PE RVA' }
                return [int]$offset
            }
        }
        throw 'Unmapped PE RVA'
    }
    foreach ($spec in @(@(1,20,12), @(13,32,4))) {
        $rva = [BitConverter]::ToUInt32($data,$optional+112+$spec[0]*8)
        if (-not $rva) { continue }
        $position = Resolve-PeRva $rva
        for ($n=0; $n -lt 10000; $n++) {
            if ($position + $spec[1] -gt $data.Length) { throw 'Truncated PE import table' }
            $nonzero = $false
            for ($i=0; $i -lt $spec[1]; $i++) { if ($data[$position+$i]) { $nonzero=$true; break } }
            if (-not $nonzero) { break }
            $start = Resolve-PeRva ([BitConverter]::ToUInt32($data,$position+$spec[2]))
            $end = $start
            while ($end -lt $data.Length -and $data[$end]) { $end++ }
            if ($end -eq $data.Length) { throw 'Unterminated PE import name' }
            [Text.Encoding]::ASCII.GetString($data,$start,$end-$start).ToLowerInvariant()
            $position += $spec[1]
        }
        if ($n -eq 10000) { throw 'Excessive PE import count' }
    }
}
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
    if ($item.Extension -in @('.py','.pyc','.pyd') -or $item.Name -match '(?i)python') { throw "Interpreter dependency must not enter beta: $($item.Name)" }
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
