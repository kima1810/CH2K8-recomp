#Requires -Version 7.0
# Prepare a normal CHMOD ABI 2 launch with a generated scorebug overlay.
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$OverlayRoot,
    [Parameter(Mandatory)][string]$ProviderDll,
    [Parameter(Mandatory)][string]$Executable,
    [Parameter(Mandatory)][string]$LaunchSettings,
    [ValidateSet('ESPN','USA Sports')][string]$Style,
    [switch]$AllowNativeCode,
    [switch]$PrepareOnly
)
$ErrorActionPreference = 'Stop'
if (-not $AllowNativeCode) { throw 'The scorebug DLL requires explicit native-code opt-in.' }

$overlay = (Resolve-Path -LiteralPath $OverlayRoot).Path
$exe = (Resolve-Path -LiteralPath $Executable).Path
$dll = (Resolve-Path -LiteralPath $ProviderDll).Path
$saved = Get-Content -LiteralPath $LaunchSettings -Raw | ConvertFrom-Json
if ('--ch2k8_renderer=d3d12' -cnotin $saved.arguments) {
    throw 'The converted scorebug overlay requires D3D12.'
}
$oldRootArg = @($saved.arguments | Where-Object { $_ -like '--game_data_root=*' })
if ($oldRootArg.Count -ne 1) { throw 'Launch settings must identify one original asset root.' }
$oldRoot = $oldRootArg[0].Substring('--game_data_root='.Length)
foreach ($file in @('chmod-lock.json','native_dds.index','native_dds_choices.index')) {
    if ((Get-FileHash -LiteralPath (Join-Path $oldRoot $file)).Hash -ne
        (Get-FileHash -LiteralPath (Join-Path $overlay $file)).Hash) {
        throw 'The enabled mods changed. Rebuild the scorebug overlay before preparing a launch.'
    }
}
if (-not (Test-Path -LiteralPath (Join-Path $overlay 'scorebug-probe.ready') -PathType Leaf)) {
    throw 'This directory is missing the generated scorebug overlay marker.'
}

$configArg = @($saved.arguments | Where-Object { $_ -like '--ch2k8_mod_config=*' })
if ($configArg.Count -ne 1) { throw 'Launch settings must identify one native mod configuration.' }
$originalConfig = $configArg[0].Substring('--ch2k8_mod_config='.Length)
$plan = Get-Content -LiteralPath $originalConfig -Raw | ConvertFrom-Json
$modRoot = (Resolve-Path -LiteralPath $plan.mod_root).Path
$hash = (Get-FileHash -LiteralPath $dll -Algorithm SHA256).Hash.ToLowerInvariant()
$package = "org.ch2k8.scorebug-$hash"
$destination = Join-Path $modRoot $package
$null = New-Item -ItemType Directory -Path $destination -Force
$installedDll = Join-Path $destination 'scorebug-preview.dll'
if (-not (Test-Path -LiteralPath $installedDll)) {
    Copy-Item -LiteralPath $dll -Destination $installedDll
}
if ((Get-FileHash -LiteralPath $installedDll).Hash.ToLowerInvariant() -ne $hash) {
    throw 'The staged scorebug DLL hash differs.'
}

$plan.extensions = @($plan.extensions | Where-Object { $_.id -ne 'org.ch2k8.scorebug' }) + @(
    [pscustomobject]@{
        id = 'org.ch2k8.scorebug'
        version = '0.1.0'
        file = "$package/scorebug-preview.dll"
        sha256 = $hash
        abi = 2
        capabilities = @('lifecycle.runtime.ready')
        replacements = @()
        dependencies = @()
    }
)
$config = Join-Path $destination 'native-mod-launch.json'
[IO.File]::WriteAllText($config, ($plan | ConvertTo-Json -Depth 16))
$flags = @($saved.arguments | Where-Object {
    $_ -notmatch '^--(game_data_root|log_file|ch2k8_mod_config|ch2k8_allow_native_mods)='
})
$log = Join-Path $destination ('scorebug-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.log')
$flags += @("--game_data_root=$overlay", "--log_file=$log",
    "--ch2k8_mod_config=$config", '--ch2k8_allow_native_mods=true')
if ($PrepareOnly) {
    [pscustomobject]@{ executable=$exe; arguments=$flags; style=$Style; configuration=$config }
    return
}
if (Get-Process ch2k8 -ErrorAction SilentlyContinue) { throw 'Close College Hoops first.' }
$start = [Diagnostics.ProcessStartInfo]::new($exe)
$start.WorkingDirectory = Split-Path -Parent $exe
$start.UseShellExecute = $false
foreach ($flag in $flags) { $start.ArgumentList.Add($flag) }
if ($Style) { $start.Environment['CH2K8_SCOREBUG_STYLE'] = $Style }
else { [void]$start.Environment.Remove('CH2K8_SCOREBUG_STYLE') }
$start.Environment['CH2K8_MODS_DISABLED'] = '0'
$null = [Diagnostics.Process]::Start($start)
