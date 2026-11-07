<#
.SYNOPSIS
Build local native RenderDoc clients against matching official replay headers.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Headers,
    [Parameter(Mandatory)][string]$RenderDoc,
    [string]$LlvmBin
)
$ErrorActionPreference = 'Stop'
$Headers = (Resolve-Path -LiteralPath $Headers).Path
$RenderDoc = (Resolve-Path -LiteralPath $RenderDoc).Path
if (-not (Test-Path -LiteralPath (Join-Path $Headers 'renderdoc_replay.h'))) {
    throw 'Headers must contain the official renderdoc/api/replay headers matching the DLL.'
}
if (-not (Test-Path -LiteralPath (Join-Path $RenderDoc 'renderdoc.dll'))) {
    throw 'RenderDoc must identify the portable installation containing renderdoc.dll.'
}
if ($LlvmBin) {
    $compiler = Join-Path $LlvmBin 'clang++.exe'
    $dlltool = Join-Path $LlvmBin 'llvm-dlltool.exe'
} else {
    $compiler = (Get-Command clang++.exe -ErrorAction Stop).Source
    $dlltool = (Get-Command llvm-dlltool.exe -ErrorAction Stop).Source
}
$repoRoot = Split-Path -Parent $PSScriptRoot
$output = Join-Path $repoRoot 'work/tooling/renderdoc-client-build'
New-Item -ItemType Directory -Path $output -Force | Out-Null
$definition = Join-Path $output 'renderdoc.def'
$library = Join-Path $output 'renderdoc.lib'
@'
LIBRARY renderdoc.dll
EXPORTS
RENDERDOC_CreateTargetControl
RENDERDOC_EnumerateRemoteTargets
RENDERDOC_AllocArrayMem
RENDERDOC_FreeArrayMem
RENDERDOC_InitialiseReplay
RENDERDOC_ShutdownReplay
RENDERDOC_OpenCaptureFile
'@ | Set-Content -LiteralPath $definition -Encoding ascii
& $dlltool -m i386:x86-64 -d $definition -l $library
if ($LASTEXITCODE) { throw "Import-library generation failed: $LASTEXITCODE" }
foreach ($name in @('capture','replay','timeline','shader_probe','shader_compare')) {
    $source = Join-Path $PSScriptRoot ('renderdoc_'+$name+'.cpp')
    $executable = Join-Path $RenderDoc ('ch2k8_'+$name+'.exe')
    & $compiler -std=c++17 -O2 -DRENDERDOC_PLATFORM_WIN32 -DNOMINMAX -isystem $Headers $source $library -o $executable
    if ($LASTEXITCODE) { throw "Build failed for $name" }
    Write-Host "Built $executable"
}
