<# Migrate startup metadata to direct component reads. Never launches the game. #>
param([string]$GameData)
$ErrorActionPreference='Stop'
$repo=Split-Path -Parent $PSScriptRoot
if (!$GameData) {$GameData=Join-Path $repo 'port/out/folder-game'}
$GameData=(Resolve-Path -LiteralPath $GameData).Path
if (Get-Process -Name ch2k8 -ErrorAction SilentlyContinue) {throw 'Close the game before changing loader metadata'}
$capabilityFile=Join-Path $GameData 'runtime_capabilities.json'
$capabilities=Get-Content -LiteralPath $capabilityFile -Raw|ConvertFrom-Json -AsHashtable
if ($capabilities.platform -ne 'xbox360') {throw 'Xbox folder runtime required'}
$backup=Join-Path $GameData ('_runtime_backups/direct-transition-'+[DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss-ffff'))
New-Item -ItemType Directory -Path $backup -Force|Out-Null
$files=@('assets.json','assets.map','native_dds.index','native_audio.index','runtime_capabilities.json');$existed=@{}
foreach ($name in $files) {
    $path=Join-Path $GameData $name;$existed[$name]=Test-Path -LiteralPath $path -PathType Leaf
    if ($existed[$name]) {Copy-Item -LiteralPath $path -Destination (Join-Path $backup $name)}
}
try {
    & (Join-Path $repo 'port/out/python-env/Scripts/python.exe') (Join-Path $PSScriptRoot 'prepare_direct_assets.py') $GameData
    if ($LASTEXITCODE) {throw "Direct folder validation failed ($LASTEXITCODE)"}
    $manifest=Get-Content -LiteralPath (Join-Path $GameData 'assets.json') -Raw|ConvertFrom-Json -AsHashtable
    $manifest.loader_metadata=Get-Content -LiteralPath (Join-Path $GameData '_runtime/compatibility.json') -Raw|ConvertFrom-Json -AsHashtable
    $manifest.storage='loose-resources';$manifest.Remove('segments');$manifest.Remove('parts')
    $manifest|ConvertTo-Json -Depth 12|Set-Content -LiteralPath (Join-Path $GameData 'assets.json') -Encoding utf8NoBOM
    $capabilities.direct_resources=$true;$capabilities.asset_storage='loose-components';$capabilities.native_dds_backend='d3d12'
    $capabilities|ConvertTo-Json -Depth 4|Set-Content -LiteralPath $capabilityFile -Encoding UTF8
} catch {
    foreach ($name in $files) {
        $path=Join-Path $GameData $name
        if ($existed[$name]) {Copy-Item -LiteralPath (Join-Path $backup $name) -Destination $path -Force}
        elseif (Test-Path -LiteralPath $path -PathType Leaf) {Remove-Item -LiteralPath $path}
    }
    throw
}
Write-Output "Direct folder loading enabled. Previous loader metadata: $backup. No game launched."
