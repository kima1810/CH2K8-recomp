<# Build and install the pinned patched SDK. Safe to rerun after an interrupted build. #>
[CmdletBinding()]
param([ValidateRange(1,16)][int]$Jobs=2,[string]$PythonExecutable,[switch]$SdkOnly,[switch]$ToolchainReady)
$ErrorActionPreference='Stop'
$repoRoot=Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'build_support.ps1')
if(-not $global:Ch2k8BuildContext){
    $folder=Join-Path $repoRoot ('port/userdata/builds/sdk-'+[DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss-ffff'))
    $null=New-Item -ItemType Directory -Path $folder -Force
    $global:Ch2k8BuildContext=@{stage='sdk-prerequisites';source='pinned-sdk';log=(Join-Path $folder 'build.log');status=(Join-Path $folder 'status.json')}
}
$PythonExecutable=Find-BuildPython $PythonExecutable $repoRoot
if(-not $ToolchainReady){$toolchain=Initialize-BuildToolchain;Test-BuildCompiler $toolchain.clang}
$source=Join-Path $repoRoot 'work/third_party/rexglue-vulkan'
$build=Join-Path $repoRoot 'port/out/build/sdk-vulkan'
$install=Join-Path $repoRoot 'port/sdk-vulkan'
$pin='bd833a2ab69d305f99ddf57418fc38ffec8af93d'
$git=(Get-Command git.exe).Source;$cmake=(Get-Command cmake.exe).Source
if(-not (Test-Path -LiteralPath $source)){
    Invoke-BuildCommand 'sdk-clone' $git @('-c','core.longpaths=true','clone','--depth','50','--branch','nightly-20261002-bd833a2a','https://github.com/rexglue/rexglue-sdk.git',$source) 'Check internet/proxy access to GitHub and retry. If a clone was interrupted before .git was created, rename that incomplete SDK source folder and rerun; no folder is deleted automatically.'
}
Write-BuildStatus 'sdk-revision' -Message 'Checking pinned SDK source'
$revision=& $git -C $source rev-parse HEAD
if($LASTEXITCODE -ne 0 -or $revision -ne $pin){throw "Expected SDK $pin; found $revision. Existing sources were preserved. Use the pinned source in $source; rename an incomplete or unrelated SDK folder before retrying."}
Invoke-BuildCommand 'sdk-submodules' $git @('-c','core.longpaths=true','-C',$source,'submodule','update','--init','--recursive','--depth','1','--jobs',"$Jobs") 'Check internet/proxy access to GitHub. Rerun the build to resume missing submodules; completed downloads are retained.'
$description=$null
try{$description=& $git -C $source describe --tags --long --match 'v[0-9]*.[0-9]*' --exclude '*-*' 2>$null}catch{}
if(-not $description){Invoke-BuildCommand 'sdk-version-history' $git @('-C',$source,'fetch','--deepen=50','origin','tag','nightly-20261002-bd833a2a')}
Invoke-BuildCommand 'sdk-patches' $PythonExecutable @('-u',"$PSScriptRoot/prepare_vulkan_sdk.py",$source) 'Use the pinned SDK revision and current tracked patch scripts together. An unrecognized SDK patch target needs a bug report with this log; do not bypass the patch check.'
$clang=(Get-Command clang++.exe).Source
$clangC=Join-Path (Split-Path -Parent $clang) 'clang.exe'
$ninja=(Get-Command ninja.exe).Source
Invoke-BuildCommand 'sdk-configure' $cmake @('-S',$source,'-B',$build,'-G','Ninja','-DCMAKE_BUILD_TYPE=Release',"-DCMAKE_C_COMPILER=$clangC","-DCMAKE_CXX_COMPILER=$clang","-DCMAKE_MAKE_PROGRAM=$ninja",'-DREXGLUE_USE_VULKAN=ON','-DREXGLUE_USE_D3D12=ON','-DREXGLUE_BUILD_TESTS=OFF','-DCMAKE_EXPORT_NO_PACKAGE_REGISTRY=ON',"-DCMAKE_INSTALL_PREFIX=$install","-DPython3_EXECUTABLE=$($PythonExecutable.Replace('\','/'))") 'Inspect the CMake error below. Ensure Desktop development with C++ and a Windows SDK are installed. A cache from another checkout/toolchain requires a separate build directory or manually moving the old SDK build folder.'
Invoke-BuildCommand 'sdk-build' $cmake @('--build',$build,'--parallel',"$Jobs") 'Inspect the final compiler/linker error. For insufficient memory, rerun with -Jobs 1. The SDK build resumes completed compilation.'
Invoke-BuildCommand 'sdk-install' $cmake @('--install',$build,'--config','Release')
if($SdkOnly){return}
Push-Location (Join-Path $repoRoot 'port')
try{
    Invoke-BuildCommand 'game-configure' $cmake @('--preset','win-amd64-vulkan',"-Drexglue_DIR=$install/lib/cmake/rexglue","-DPython3_EXECUTABLE=$($PythonExecutable.Replace('\','/'))")
    Invoke-BuildCommand 'game-build' $cmake @('--build','--preset','win-amd64-vulkan','--parallel',"$Jobs")
}finally{Pop-Location}
