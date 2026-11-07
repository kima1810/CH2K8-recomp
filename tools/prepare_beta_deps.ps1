<# Prepare redistributable dependencies once on the maintainer machine. #>
[CmdletBinding()]
param([string]$CrtDirectory)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSHOME 'Modules/Microsoft.PowerShell.Utility')
$repo = Split-Path -Parent $PSScriptRoot
$destination = Join-Path $repo 'out/beta-deps'
$null = New-Item -ItemType Directory -Path $destination -Force
if (-not $CrtDirectory) {
    $candidates = Get-ChildItem 'C:/Program Files (x86)/Microsoft Visual Studio/*/BuildTools/VC/Redist/MSVC/*/x64/Microsoft.VC*.CRT' -Directory -ErrorAction SilentlyContinue | Sort-Object FullName -Descending
    if ($candidates) { $CrtDirectory = $candidates[0].FullName }
}
if (-not $CrtDirectory) { throw 'Specify -CrtDirectory with the x64 Microsoft Visual C++ redistributable CRT folder from Visual Studio.' }
$crt = Join-Path $destination 'crt'
$null = New-Item -ItemType Directory -Path $crt -Force
foreach ($name in @('msvcp140.dll', 'msvcp140_atomic_wait.dll', 'vcruntime140.dll', 'vcruntime140_1.dll')) {
    Copy-Item -LiteralPath (Join-Path $CrtDirectory $name) -Destination $crt -Force
}
$controllerPin = '07af1d50187e94c861c9f9f5d8a55b148f11306b'
foreach ($entry in @(@('gamecontrollerdb.txt', 'gamecontrollerdb.txt', '4ef169fcee14ef9563e36ebf731dc6950494e553bf8b56b5fc8aa70181f0d25c'), @('LICENSE', 'CONTROLLER_LICENSE.txt', '97f35b302b361680ec1e891e95d2d52097bb95abff361434916d99dc1305f127'))) {
    $file = Join-Path $destination $entry[1]
    if (-not (Test-Path -LiteralPath $file)) {
        Invoke-WebRequest -UseBasicParsing -Uri "https://raw.githubusercontent.com/mdqinc/SDL_GameControllerDB/$controllerPin/$($entry[0])" -OutFile $file
    }
    if ((Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry[2]) { throw 'Controller database/license checksum mismatch.' }
}
Write-Output "Beta dependencies prepared at $destination"
