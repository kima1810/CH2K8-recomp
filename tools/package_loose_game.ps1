<# Package the built game alongside its imported Xbox folders; never launches it. #>
[CmdletBinding()]
param(
    [string]$GameData,
    [string]$BuildDirectory
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
if (-not $GameData) { $GameData = Join-Path $repo 'port/out/folder-game' }
if (-not $BuildDirectory) { $BuildDirectory = Join-Path $repo 'port/out/build/win-amd64-vulkan' }
$GameData = (Resolve-Path -LiteralPath $GameData).Path
$BuildDirectory = (Resolve-Path -LiteralPath $BuildDirectory).Path
if (Get-Process -Name ch2k8 -ErrorAction SilentlyContinue) {throw 'Close the game before updating its runtime files'}
foreach ($name in @('assets.json','assets.map','native_dds.index','default.xex')) {
    if (-not (Test-Path -LiteralPath (Join-Path $GameData $name) -PathType Leaf)) { throw "Incomplete folder installation: $name" }
}
$runtimeFiles=@('ch2k8.exe','rexgpu-xenos.dll','rexruntime.dll')
foreach ($name in $runtimeFiles) {
    $source = Join-Path $BuildDirectory $name
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw "Build file missing: $source" }
}
$backup=Join-Path $GameData ('_runtime_backups/'+[DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss-ffff'))
New-Item -ItemType Directory -Path $backup -Force | Out-Null
foreach ($name in ($runtimeFiles+@('runtime_capabilities.json'))) {
    $existing=Join-Path $GameData $name
    if (Test-Path -LiteralPath $existing -PathType Leaf) {Copy-Item -LiteralPath $existing -Destination (Join-Path $backup $name)}
}
foreach ($name in $runtimeFiles) {
    $source = Join-Path $BuildDirectory $name
    Copy-Item -LiteralPath $source -Destination (Join-Path $GameData $name) -Force
}
$capabilities=@{version=1;platform='xbox360';native_dds_formats=@(18,19,20,49,59);native_dds_backend='d3d12';native_pcm=$true;added_asset_banks=$true;growing_roster=$true;direct_resources=$true;asset_storage='loose-components';runtime_acceptance='manual testing pending';binaries=@{}}
foreach ($name in $runtimeFiles) {$capabilities.binaries[$name]=(Get-FileHash -LiteralPath (Join-Path $GameData $name) -Algorithm SHA256).Hash.ToLowerInvariant()}
$capabilities|ConvertTo-Json -Depth 4|Set-Content -LiteralPath (Join-Path $GameData 'runtime_capabilities.json') -Encoding UTF8
if (Test-Path -LiteralPath (Join-Path $BuildDirectory 'ch2k8.pdb')) {
    Copy-Item -LiteralPath (Join-Path $BuildDirectory 'ch2k8.pdb') -Destination (Join-Path $GameData 'ch2k8.pdb') -Force
}
$launcher = (Join-Path $repo 'tools/launch_ch2k8.ps1').Replace("'", "''")
Copy-Item -LiteralPath (Join-Path $repo 'port/third_party/XENIA_TEXTURE_LICENSE.txt') -Destination (Join-Path $GameData 'XENIA_TEXTURE_LICENSE.txt') -Force
$entry = @'
$ErrorActionPreference = 'Stop'
& '__LAUNCHER__' -Renderer d3d12 -GameData $PSScriptRoot -Executable (Join-Path $PSScriptRoot 'ch2k8.exe')
'@
$entry.Replace('__LAUNCHER__', $launcher) | Set-Content -LiteralPath (Join-Path $GameData 'Launch Folder Game.ps1') -Encoding UTF8
'@echo off', 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Launch Folder Game.ps1"' |
    Set-Content -LiteralPath (Join-Path $GameData 'Launch Folder Game.cmd') -Encoding ASCII
@'
Xbox folder installation -- D3D12 native DDS replacements

Open "Launch Folder Game.cmd" and click Launch. The launcher validates edits
and prepares changed resource overlays before starting the game.

Edit assets/<bank>.iff/<record>.scne/blockN.dat, .rost/blockN.dat, etc.
Components retain their original byte length except the checked growing roster
payload. record.json describes
identities; it is not a semantic editor. Do not edit .stored files or manifests.

Supported TXTR folders contain texture.dds. Keep the BC1/BC2/BC3/BC4/BC5 format and aspect
ratio; power-of-two upscales (up to 8192 pixels) and mip chains are supported.
Unchanged DDS templates preserve the game's original mipmapped rendering.
Unsupported texture layouts retain editable binary components, with the reason
recorded in asset.json. DDS files and resource edits are applied after restart.

No physical 0A..0M archive chunks are required here. Unknown/CDF entries retain
payload.dat for replacement by a format-aware editor. Source ISO/disc is untouched.
This local launcher uses the tools and Python environment in the source checkout.
See docs/formats/loose_assets.md in that checkout for limits and test instructions.
'@ | Set-Content -LiteralPath (Join-Path $GameData 'EDITING.txt') -Encoding UTF8
Write-Output "Folder game packaged at $GameData. The game was not launched."
