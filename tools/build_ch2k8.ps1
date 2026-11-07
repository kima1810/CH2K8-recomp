<# Build from a supported retail XEX, extracted disc folder or ISO. #>
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Source,
    [string]$PythonExecutable,[string]$SdkDirectory,[string]$BuildDirectory,
    [string]$InstallDirectory,
    [ValidateRange(1,16)][int]$Jobs=2,
    [switch]$CodeOnly,[switch]$ValidateOnly,[string]$LogFile
)
$ErrorActionPreference='Stop'
Import-Module (Join-Path $PSHOME 'Modules/Microsoft.PowerShell.Utility')
. (Join-Path $PSScriptRoot 'build_support.ps1')
$repo=Split-Path -Parent $PSScriptRoot
if(-not $LogFile){$LogFile=Join-Path $repo ('port/userdata/builds/'+[DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss-ffff')+'/build.log')}
$LogFile=$ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($LogFile)
$null=New-Item -ItemType Directory -Path (Split-Path -Parent $LogFile) -Force
$global:Ch2k8BuildContext=@{stage='input';source=$Source;log=$LogFile;status=(Join-Path (Split-Path -Parent $LogFile) 'status.json')}
$failureCode=1
$buildLock=$null
try {
    Write-BuildStatus 'input' -Message 'Checking source and output paths'
    if(-not (Test-Path -LiteralPath $Source)){throw "Input not found: $Source. Select your ISO, original default.xex, or extracted disc folder."}
    $Source=(Resolve-Path -LiteralPath $Source).Path
    $kind=if(Test-Path -LiteralPath $Source -PathType Container){'folder'}elseif([IO.Path]::GetExtension($Source) -ieq '.iso'){'iso'}elseif([IO.Path]::GetExtension($Source) -ieq '.xex'){'xex'}else{throw 'Select an Xbox 360 College Hoops 2K8 ISO or default.xex. ZIP/7z, GOD/STFS containers and PS3 discs must first be converted/extracted using their appropriate tools.'}
    $expected='71e8983d1cc009e485696aad19b5fa4b4661761870e2c8972717b932c1e4be36'
    $xex=if($kind -eq 'folder'){Join-Path $Source 'default.xex'}elseif($kind -eq 'xex'){$Source}else{$null}
    if($xex){
        if(-not (Test-Path -LiteralPath $xex -PathType Leaf)){throw "No default.xex in $Source. Select the disc root, not its parent folder."}
        $actual=(Get-FileHash -LiteralPath $xex -Algorithm SHA256).Hash.ToLowerInvariant()
        if($actual -ne $expected){throw "Unsupported XEX revision. Observed SHA256: $actual; compiled revision: $expected. This does not determine whether your copy is legitimate. A different executable needs revision-specific code generation/configuration; include this hash in a compatibility report. Original input was left unchanged."}
    }
    if(-not $SdkDirectory){$SdkDirectory=Join-Path $repo 'port/sdk-vulkan'}
    if(-not $BuildDirectory){$BuildDirectory=Join-Path $repo 'port/out/build/win-amd64-vulkan'}
    $SdkDirectory=$ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($SdkDirectory)
    $BuildDirectory=$ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($BuildDirectory)
    if($InstallDirectory){$InstallDirectory=$ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($InstallDirectory)}
    Write-BuildStatus 'prerequisites' -Message 'Finding Python, Microsoft C++ tools, Windows SDK, CMake, LLVM, Ninja and Git'
    $python=Find-BuildPython $PythonExecutable $repo
    $tools=Initialize-BuildToolchain
    $cmake=$tools.cmake;$clang=$tools.clang;$ninja=$tools.ninja
    Test-BuildCompiler $clang
    if(-not $PSBoundParameters.ContainsKey('Jobs')){
        try{
            $memory=Get-CimInstance Win32_ComputerSystem -ErrorAction Stop
            if([uint64]$memory.TotalPhysicalMemory -lt 12GB){$Jobs=1;Write-BuildMessage 'Using one compiler job on this memory-limited PC. Pass -Jobs explicitly to override.'}
        }catch{Write-BuildMessage 'Memory detection unavailable; using the conservative default of two compiler jobs.'}
    }
    $pythonCMake=$python.Replace('\','/')
    $plan=[pscustomobject]@{source=$Source;source_kind=$kind;python=$python;cmake=$cmake;clang=$clang;ninja=$ninja;git=$tools.git;visual_studio=$tools.visual_studio;vc_tools=$tools.vc_tools;windows_sdk=$tools.windows_sdk;jobs=$Jobs;sdk=$SdkDirectory;build_directory=$BuildDirectory;install_directory=$InstallDirectory;code_only=[bool]$CodeOnly;xex_alone_needs_assets_for_play=$true;log=$LogFile;status=$global:Ch2k8BuildContext.status}
    $plan|ConvertTo-Json|Set-Content -LiteralPath (Join-Path (Split-Path -Parent $LogFile) 'environment.json') -Encoding UTF8
    if($ValidateOnly){Write-BuildStatus 'prerequisites' 'validated' 'Prerequisites passed. ISO identity is checked by native extraction before SDK compilation.';$plan|ConvertTo-Json;return}
    Write-BuildStatus 'workspace-lock' -Message 'Reserving this source checkout for one build'
    $lockPath=Join-Path $repo 'port/userdata/source-build.lock'
    $null=New-Item -ItemType Directory -Path (Split-Path -Parent $lockPath) -Force
    try{$buildLock=[IO.File]::Open($lockPath,[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)}catch{throw 'Another source build is using this checkout. Wait for it to finish, or use a separate checkout. An abandoned lock file is harmless; only a live process holds the lock.'}
    if($repo.Length -gt 130){Write-BuildMessage 'Warning: source paths are very long. If a third-party compiler fails on a path, move the source checkout to a short local path such as C:/dev/CH2K8; native asset paths support extended lengths.'}
    $native=Join-Path $repo 'out/native-tools/ch2k8_tools.exe'
    Invoke-BuildCommand 'native-configure' $cmake @('-S',"$repo/tools/native_assets",'-B',"$repo/out/native-tools",'-G','Ninja',"-DCMAKE_CXX_COMPILER=$clang",'-DCMAKE_BUILD_TYPE=Release',"-DCMAKE_MAKE_PROGRAM=$ninja")
    Invoke-BuildCommand 'native-build' $cmake @('--build',"$repo/out/native-tools",'--parallel',"$Jobs")
    $stagedXex=Join-Path $repo 'work/ch2k8/XBOX/disc/default.xex'
    $null=New-Item -ItemType Directory -Path (Split-Path -Parent $stagedXex) -Force
    if((Test-Path -LiteralPath $stagedXex) -and (Get-FileHash -LiteralPath $stagedXex).Hash.ToLowerInvariant() -ne $expected){throw 'Existing code-generation XEX differs. It was left untouched. Use a separate clean checkout for another executable revision.'}
    if($kind -eq 'iso'){
        Invoke-BuildCommand 'iso-executable' $native @('extract-xex',$Source,$stagedXex) 'Check the ISO error and executable hash below. Use a complete Xbox 360 disc image or extracted disc root. Different executable revisions require a compatibility report; changing the hash gate cannot make fixed-address generated code compatible.'
    }elseif(-not (Test-Path -LiteralPath $stagedXex)){Copy-Item -LiteralPath $xex -Destination $stagedXex}
    $sdkFiles=@('bin/rexglue.exe','lib/cmake/rexglue/rexglueConfig.cmake','bin/rexruntime.dll','bin/rexgpu-xenos.dll')
    $missing=@($sdkFiles|Where-Object{-not (Test-Path -LiteralPath (Join-Path $SdkDirectory $_))})
    if($missing.Count){
        if($SdkDirectory -ne (Join-Path $repo 'port/sdk-vulkan')){throw "Selected SDK is incomplete ($($missing -join ', ')). Choose a fully installed patched SDK, or omit -SdkDirectory to build it automatically."}
        & (Join-Path $PSScriptRoot 'build_vulkan_sdk.ps1') -Jobs $Jobs -PythonExecutable $python -SdkOnly -ToolchainReady
    }
    Push-Location (Join-Path $repo 'port')
    try{
        Invoke-BuildCommand 'code-generation' $python @('-u',"$repo/tools/run_codegen.py","$SdkDirectory/bin/rexglue.exe","$repo/port/ch2k8_manifest.toml","$repo/port/generated/default") 'Check the codegen error below. Do not substitute another title/revision. Confirm the supported XEX and the pinned patched SDK; rerun after correcting the cause.'
        Invoke-BuildCommand 'game-configure' $cmake @('-S',"$repo/port",'-B',$BuildDirectory,'-G','Ninja',"-DCMAKE_CXX_COMPILER=$clang","-DCMAKE_MAKE_PROGRAM=$ninja",'-DCMAKE_BUILD_TYPE=Release',"-DCMAKE_PREFIX_PATH=$SdkDirectory","-Drexglue_DIR=$SdkDirectory/lib/cmake/rexglue",'-DCH2K8_REQUIRE_VULKAN=ON',"-DPython3_EXECUTABLE=$pythonCMake") 'Read the CMake error below. For a cache from another checkout/toolchain, pass a new -BuildDirectory; existing build outputs are never deleted automatically.'
        Invoke-BuildCommand 'game-build' $cmake @('--build',$BuildDirectory,'--target','ch2k8','ch2k8_tools','--parallel',"$Jobs") 'Check the final compiler/linker error below. For memory exhaustion rerun with -Jobs 1. Use a new -BuildDirectory for a stale CMake cache; completed code generation is reused.'
    }finally{Pop-Location}
    $gameData=if($kind -eq 'folder'){$Source}elseif($kind -eq 'xex'){Split-Path -Parent $Source}else{$null}
    if($kind -eq 'iso' -and -not $CodeOnly){
        $gameData=if($InstallDirectory){$InstallDirectory}else{Join-Path $repo ('work/installed/'+[IO.Path]::GetFileNameWithoutExtension($Source)+'-assets')}
        if(Test-Path -LiteralPath $gameData){
            if(-not (Test-Path -LiteralPath (Join-Path $gameData 'assets.json')) -or -not (Test-Path -LiteralPath (Join-Path $gameData 'default.xex')) -or (Get-FileHash -LiteralPath (Join-Path $gameData 'default.xex')).Hash.ToLowerInvariant() -ne $expected){throw 'Existing ISO installation is incomplete or incompatible. It was left untouched. Pass -InstallDirectory with a new folder to retry.'}
            Invoke-BuildCommand 'asset-prepare' $native @('prepare',$gameData)
        }else{
            Invoke-BuildCommand 'iso-assets' $native @('import',$Source,$gameData,'--progress-file',(Join-Path (Split-Path -Parent $LogFile) 'asset-progress.json')) 'The game executable is already built. Check the importer error/free disk space. Retry with -InstallDirectory on a drive with room for decoded assets; use -CodeOnly if you only need the executable.'
        }
        Invoke-BuildCommand 'runtime-map' $native @('validate-runtime',$gameData)
    }
    $ready=[bool]($gameData -and ((Test-Path -LiteralPath (Join-Path $gameData '0A')) -or (Test-Path -LiteralPath (Join-Path $gameData 'assets.map'))))
    $result=@{executable=(Join-Path $BuildDirectory 'ch2k8.exe');game_data=$gameData;data_ready=$ready;source_kind=$kind;python=$python;log=$LogFile;status=$global:Ch2k8BuildContext.status}
    if(-not (Test-Path -LiteralPath $result.executable)){throw 'Build completed without the expected ch2k8.exe. Inspect CMake output and the selected build directory.'}
    $state=Join-Path $repo 'port/userdata';$null=New-Item -ItemType Directory -Path $state -Force
    $result|ConvertTo-Json|Set-Content -LiteralPath (Join-Path $state 'build-result.json') -Encoding UTF8
    if($gameData){@{game_data=$gameData;renderer='d3d12';executable=$result.executable}|ConvertTo-Json|Set-Content -LiteralPath (Join-Path $state 'launcher.json') -Encoding UTF8}
    Write-BuildStatus 'complete' 'succeeded' 'Recompilation built. Use Check setup before playing.'
    $result|ConvertTo-Json
}catch{
    $message=$_.Exception.Message
    $current=Get-Content -LiteralPath $global:Ch2k8BuildContext.status -Raw -ErrorAction SilentlyContinue|ConvertFrom-Json
    if(-not $current -or $current.state -ne 'failed'){Write-BuildStatus $global:Ch2k8BuildContext.stage 'failed' $message 'Correct the reported input/prerequisite, then rerun the same command. No source game files were modified.' $failureCode}
    Write-BuildMessage ($_.ScriptStackTrace)
    throw "$message`nBuild log: $LogFile`nStatus report: $($global:Ch2k8BuildContext.status)"
}finally{if($buildLock){$buildLock.Dispose()}}
