<# Build a portable beta ZIP from existing compiled output. No game data is included. #>
[CmdletBinding()]
param([string]$BuildDirectory, [string]$OutputDirectory, [string]$CrtDirectory, [string]$RuntimeSourceRevision, [string]$SdkRuntimeSourceRevision)
$ErrorActionPreference = 'Stop'
# A caller using PowerShell 7 may pass a module path without Windows modules.
Import-Module (Join-Path $PSHOME 'Modules/Microsoft.PowerShell.Utility')
$repo = Split-Path -Parent $PSScriptRoot
if (-not $BuildDirectory) { $BuildDirectory = if(Test-Path -LiteralPath (Join-Path $repo 'ch2k8.exe')){$repo}else{Join-Path $repo 'port/out/build/win-amd64-vulkan'} }
if (-not $OutputDirectory) { $OutputDirectory = Join-Path $repo 'out/beta' }
if (-not $CrtDirectory) { $CrtDirectory = if(Test-Path -LiteralPath (Join-Path $repo 'vcruntime140.dll')){$repo}else{Join-Path $repo 'out/beta-deps/crt'} }
$crtFiles = @('msvcp140.dll', 'msvcp140_atomic_wait.dll', 'vcruntime140.dll', 'vcruntime140_1.dll')
foreach ($name in $crtFiles) {
    if (-not (Test-Path -LiteralPath (Join-Path $CrtDirectory $name) -PathType Leaf)) { throw "C++ runtime missing: $name. Run tools/prepare_beta_deps.ps1 first." }
}
$controllerRoot = if(Test-Path -LiteralPath (Join-Path $repo 'gamecontrollerdb.txt')){$repo}else{Join-Path $repo 'out/beta-deps'}
foreach ($name in @('gamecontrollerdb.txt', 'CONTROLLER_LICENSE.txt')) {
    if (-not (Test-Path -LiteralPath (Join-Path $controllerRoot $name) -PathType Leaf)) { throw 'Controller mappings missing. Run tools/prepare_beta_deps.ps1.' }
}
$runtime = @('ch2k8.exe', 'rexruntime.dll', 'rexgpu-xenos.dll', 'ch2k8_tools.exe')
foreach ($name in $runtime) {
    if (-not (Test-Path -LiteralPath (Join-Path $BuildDirectory $name) -PathType Leaf)) { throw "Build file missing: $name" }
}
$stage = Join-Path $OutputDirectory ('ZMO-beta1-' + [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss-ffff'))
$null = New-Item -ItemType Directory -Path (Join-Path $stage 'tools') -Force
Copy-Item -LiteralPath (Join-Path $controllerRoot 'gamecontrollerdb.txt') -Destination $stage
Copy-Item -LiteralPath (Join-Path $controllerRoot 'CONTROLLER_LICENSE.txt') -Destination $stage
foreach ($name in $crtFiles) { Copy-Item -LiteralPath (Join-Path $CrtDirectory $name) -Destination $stage }
foreach ($name in $runtime) { Copy-Item -LiteralPath (Join-Path $BuildDirectory $name) -Destination $stage }
foreach ($name in @('verify_beta.ps1', 'launch_ch2k8.ps1', 'start_launcher.ps1', 'beta_diagnostics.ps1', 'chmod.ps1', 'chmod_stage.cs', 'chmod_ui.ps1', 'runtime_update.ps1', 'update_runtime.ps1', 'pe_imports.ps1')) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination (Join-Path $stage 'tools')
}
foreach($relative in @('formats/chmod.schema.json','formats/chmod-1.1.md','formats/chmod-1.2.md','formats/chmod-1.3.md','formats/hook_registry.json','findings/2026-11-08-chmod-backend.md','findings/2026-11-08-chmod-api12.md','findings/2026-11-08-extension-framework.md','CHMOD_ACCEPTANCE.md','CHMOD_STATUS.md','RUNTIME_UPDATES.md')){
    $destination=Join-Path $stage ('docs/'+$relative)
    $null=New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force
    Copy-Item -LiteralPath (Join-Path $repo ('docs/'+$relative)) -Destination $destination
}
$receipt=Join-Path $BuildDirectory 'chmod-runtime.json'
if(Test-Path -LiteralPath $receipt){
    $metadata=Get-Content -LiteralPath $receipt -Raw|ConvertFrom-Json
    if($metadata.exe_sha256 -cne (Get-FileHash -LiteralPath (Join-Path $stage 'ch2k8.exe')).Hash.ToLowerInvariant()){throw 'Native runtime receipt does not match executable'}
    Copy-Item -LiteralPath $receipt -Destination $stage
    if([version]$metadata.mod_api -ge [version]'1.3.0'){
        [ordered]@{format=1;bootstrap_protocol=1;platform='windows-x64';package_type='runtime';xex_sha256=$metadata.xex_sha256;mod_api=$metadata.mod_api}|ConvertTo-Json|Set-Content -LiteralPath (Join-Path $stage 'runtime-update.json') -Encoding UTF8
    }
}
$null=New-Item -ItemType Directory -Path (Join-Path $stage 'examples') -Force
Copy-Item -LiteralPath (Join-Path $repo 'examples/synthetic-art.chmod'),(Join-Path $repo 'examples/native-weight-example.chmod'),(Join-Path $repo 'examples/README.md') -Destination (Join-Path $stage 'examples')
foreach($mode in @('observe','transform','replace')){Copy-Item -LiteralPath (Join-Path $repo ('examples/native-'+$mode+'-example.chmod')) -Destination (Join-Path $stage 'examples')}
Copy-Item -LiteralPath (Join-Path $repo 'port/src/mod_extension_abi.h') -Destination (Join-Path $stage 'docs/mod_extension_abi.h')
Copy-Item -LiteralPath (Join-Path $repo 'sdk') -Destination (Join-Path $stage 'sdk') -Recurse
Copy-Item -LiteralPath (Join-Path $repo 'Launch CH2K8.cmd') -Destination $stage
Copy-Item -LiteralPath (Join-Path $repo 'BETA_TESTING.md') -Destination $stage
Copy-Item -LiteralPath (Join-Path $repo 'BETA.md') -Destination (Join-Path $stage 'START HERE.md')
Copy-Item -LiteralPath (Join-Path $repo 'port/third_party/XENIA_TEXTURE_LICENSE.txt') -Destination $stage
Copy-Item -LiteralPath (Join-Path $repo 'port/third_party/NATIVE_ASSET_LICENSES.txt') -Destination $stage
$prebuiltLicenses=Join-Path $BuildDirectory 'licenses'
if(Test-Path -LiteralPath $prebuiltLicenses){Copy-Item -LiteralPath $prebuiltLicenses -Destination (Join-Path $stage 'licenses') -Recurse}
$licenses = Join-Path $repo 'port/sdk-vulkan/licenses'
if (Test-Path -LiteralPath $licenses) { Copy-Item -LiteralPath $licenses -Destination (Join-Path $stage 'licenses') -Recurse }
$sdkSource = Join-Path $repo 'work/third_party/rexglue-vulkan'
if (Test-Path -LiteralPath (Join-Path $sdkSource 'LICENSE')) {
    $null = New-Item -ItemType Directory -Path (Join-Path $stage 'licenses/rexglue') -Force
    Copy-Item -LiteralPath (Join-Path $sdkSource 'LICENSE') -Destination (Join-Path $stage 'licenses/rexglue/LICENSE')
    # Preserve third-party copyright and license notices alongside the runtime.
    Get-ChildItem -LiteralPath (Join-Path $sdkSource 'thirdparty') -File -Recurse | Where-Object { $_.Name -match '^(LICENSE|COPYING|NOTICE)([._-].*)?$' } | ForEach-Object {
        $relative = $_.FullName.Substring($sdkSource.Length + 1)
        $destination = Join-Path (Join-Path $stage 'licenses/rexglue') $relative
        $null = New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force
        Copy-Item -LiteralPath $_.FullName -Destination $destination
    }
}
$revision = & git -C $repo rev-parse HEAD
if ($LASTEXITCODE -ne 0) { throw 'Cannot identify source revision.' }
$buildHashes = @{}
foreach ($name in $runtime) { $buildHashes[$name] = (Get-FileHash -LiteralPath (Join-Path $stage $name) -Algorithm SHA256).Hash.ToLowerInvariant() }
$dirty = [bool](& git -C $repo status --porcelain --untracked-files=normal)
@{version='ZMO-beta1';source_revision=$revision;built_utc=[DateTime]::UtcNow.ToString('o');game_data_included=$false;runtime_source_revision=$RuntimeSourceRevision;sdk_runtime_source_revision=$SdkRuntimeSourceRevision;asset_tools='native';platform='windows-x64';cpu_minimum='SSE4.1';build_files=$buildHashes;source_dirty=$dirty;controller_db_revision='07af1d50187e94c861c9f9f5d8a55b148f11306b'} |
    ConvertTo-Json | Set-Content -LiteralPath (Join-Path $stage 'beta-version.json') -Encoding UTF8
Get-ChildItem -LiteralPath $stage -File -Recurse | ForEach-Object {
    (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant() + '  ' + $_.FullName.Substring($stage.Length + 1)
} | Set-Content -LiteralPath (Join-Path $stage 'SHA256SUMS.txt') -Encoding ASCII
# Reject incomplete x64 DLL dependency closures before creating a distributable.
& (Join-Path $stage 'tools/verify_beta.ps1') -Root $stage | Out-Null
$zip = Join-Path $OutputDirectory ('CH2K8-ZMO-beta1-Windows-x64-'+$revision.Substring(0,7)+'-'+[DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss-ffff')+'.zip')
Add-Type -AssemblyName System.IO.Compression.FileSystem
[IO.Compression.ZipFile]::CreateFromDirectory($stage, $zip, [IO.Compression.CompressionLevel]::Optimal, $true)
Write-Output "Beta package: $zip"
