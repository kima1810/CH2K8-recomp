# Starts the private scorebug preview with the normal launch's saved settings.
param(
    [Parameter(Mandatory=$true)][string]$OverlayRoot,
    [Parameter(Mandatory=$true)][string]$ProviderDll,
    [string]$Executable = ''
)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
$overlay = (Resolve-Path -LiteralPath $OverlayRoot).Path
$preview = Split-Path -Parent $overlay
$exe = if ($Executable) { (Resolve-Path -LiteralPath $Executable).Path } else { Join-Path $repo 'ch2k8.exe' }
$dll = (Resolve-Path -LiteralPath $ProviderDll).Path
$saved = Get-Content -LiteralPath (Join-Path $repo 'port\userdata\last-launch.json') -Raw | ConvertFrom-Json
$cache = ($saved.arguments | Where-Object { $_ -like '--game_data_root=*' }).Substring(17)
$profile = ($saved.arguments | Where-Object { $_ -like '--user_data_root=*' }).Substring(17)
if (-not (Test-Path -LiteralPath (Join-Path $profile 'chmod-profile.json'))) {
    throw 'Launch the regular game with your mods to select its save profile, then close it.'
}
foreach ($file in @('chmod-lock.json','native_dds.index','native_dds_choices.index')) {
    if ((Get-FileHash -LiteralPath (Join-Path $cache $file)).Hash -ne (Get-FileHash -LiteralPath (Join-Path $overlay $file)).Hash) {
        throw 'The enabled mods changed. Rebuild the preview overlay before testing.'
    }
}
if (Get-Process ch2k8 -ErrorAction SilentlyContinue) { throw 'Close College Hoops first.' }
$env:CH2K8_SCOREBUG_PROVIDER = (Resolve-Path -LiteralPath $dll).Path
$env:CH2K8_TRACE_SCOREBUG = '1'
$env:CH2K8_MODS_DISABLED = '0'
$log = Join-Path $preview ('runtime-combined-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.log')
$flags = @($saved.arguments | Where-Object { $_ -notlike '--game_data_root=*' -and $_ -notlike '--log_file=*' })
$flags += @("--game_data_root=$overlay","--log_file=$log")
$quoted = @($flags | ForEach-Object { if ($_ -match '\s') { '"' + $_ + '"' } else { $_ } })
Start-Process -FilePath $exe -ArgumentList $quoted -WorkingDirectory (Split-Path -Parent $exe)
