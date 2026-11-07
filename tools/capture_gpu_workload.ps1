<# Bounded, process-scoped D3D12 ROV capture. No game input is required. #>
[CmdletBinding()]
param(
    [ValidateSet('baseline','optimized')][string]$ShaderState = 'baseline',
    [ValidateSet('default','baseline','optimized')][string]$DepthState = 'default',
    [ValidateSet('default','baseline','optimized')][string]$FullWrite = 'default',
    [ValidateSet('default','baseline','optimized','compare')][string]$VertexFetch = 'default',
    [switch]$DumpShaders,
    [ValidateRange(20,600)][int]$DelaySeconds = 120,
    [ValidateRange(40,900)][int]$DurationSeconds = 200,
    [string]$Executable, [string]$GameData, [string]$RenderDoc,
    [switch]$Keyboard,
    [switch]$GpuStats,
    [switch]$ManualTrigger,
    [switch]$ValidateOnly
)
$ErrorActionPreference = 'Stop'
if ($DurationSeconds -lt $DelaySeconds+20) { throw 'Duration must exceed capture delay by at least 20 seconds.' }
$repo = Split-Path -Parent $PSScriptRoot
if (!$Executable) {$Executable=Join-Path $repo 'port/out/build/win-amd64-vulkan/ch2k8.exe'}
if (!$GameData) {$GameData=Join-Path $repo 'work/ch2k8/XBOX/disc'}
if (!$RenderDoc) {$RenderDoc=Join-Path $repo 'work/tooling/renderdoc-1.47/RenderDoc_1.47_64/renderdoccmd.exe'}
$Executable=(Resolve-Path -LiteralPath $Executable).Path
$GameData=(Resolve-Path -LiteralPath $GameData).Path
$RenderDoc=(Resolve-Path -LiteralPath $RenderDoc).Path
if (!(Test-Path -LiteralPath (Join-Path $GameData 'default.xex'))) {throw 'GameData must contain default.xex.'}
$run=Join-Path $repo ('port/out/render-diagnostics/'+(Get-Date -Format 'yyyyMMdd-HHmmss-fff')+'-capture-'+$ShaderState)
$arguments=@('capture','-d',(Split-Path $Executable),$Executable,
    '--gpu_plugin=xenos','--ch2k8_renderer=d3d12','--render_target_path_d3d12=rov',
    "--game_data_root=$GameData",("--user_data_root="+(Join-Path $repo 'port/userdata')),
    '--resolution=1280x720','--no-fullscreen','--no-fullscreen_exclusive',
    "--log_file=$run/runtime.log","--ch2k8_frame_log=$run/guest-frames.csv",
    "--ch2k8_gpu_capture=$run/device","--ch2k8_gpu_capture_delay=$DelaySeconds",
    "--ch2k8_output_capture=$run/output",'--ch2k8_output_capture_count=1',
    "--ch2k8_output_capture_delay=$($DelaySeconds+10)")
$arguments += if($ShaderState -eq 'optimized') {'--ch2k8_native_pixel_state'} else {'--no-ch2k8_native_pixel_state'}
if($DepthState -ne 'default') {
    $arguments += if($DepthState -eq 'optimized') {'--ch2k8_native_depth_state'} else {'--no-ch2k8_native_depth_state'}
}
if($Keyboard) {$arguments += '--mnk_mode'}
if($GpuStats) {$arguments += '--ch2k8_gpu_stats'}
if($ManualTrigger) {$arguments += "--ch2k8_gpu_capture_trigger=$run/capture.trigger"}
if ($FullWrite -ne 'default') {
    $arguments += if ($FullWrite -eq 'optimized') {'--ch2k8_native_full_write'} else {'--no-ch2k8_native_full_write'}
}
if ($VertexFetch -ne 'default') {
    $arguments += if ($VertexFetch -eq 'baseline') {'--no-ch2k8_native_vertex_fetch'} else {'--ch2k8_native_vertex_fetch'}
    if ($VertexFetch -eq 'compare') { $arguments += '--ch2k8_vertex_fetch_compare' }
}
if ($DumpShaders) { $arguments += @("--dump_shaders=$run/shaders", '--d3d12_dxbc_disasm', '--no-store_shaders') }
foreach($argument in $arguments) {if($argument.Contains('"')) {throw 'Arguments must not contain double quotes.'}}
$configuration=@{arguments=$arguments;run_root=$run;shader_state=$ShaderState;duration_seconds=$DurationSeconds;manual_trigger=[bool]$ManualTrigger;matched_scene=$false}
if($ValidateOnly) {$configuration | ConvertTo-Json -Depth 4;return}
if(Get-Process ch2k8 -ErrorAction SilentlyContinue) {throw 'CH2K8 is already running.'}
New-Item -ItemType Directory -Path $run | Out-Null
$started=Get-Date
$configuration.started=$started.ToString('o')
$configuration.executable_sha256=(Get-FileHash -LiteralPath $Executable).Hash
$configuration.gpu_sha256=(Get-FileHash -LiteralPath (Join-Path (Split-Path $Executable) 'rexgpu-xenos.dll')).Hash
$game=$null
try {
    $launcher=Start-Process -FilePath $RenderDoc -ArgumentList ($arguments | ForEach-Object {'"'+$_+'"'}) -WindowStyle Hidden -PassThru -RedirectStandardOutput ($run+'/capture-tool.txt')
    $timer=[Diagnostics.Stopwatch]::StartNew()
    while(!$game -and $timer.Elapsed.TotalSeconds -lt 10) {
        $candidates=@(Get-Process ch2k8 -ErrorAction SilentlyContinue | Where-Object {$_.StartTime -ge $started -and $_.Path -eq $Executable})
        if($candidates.Count -gt 1) {throw 'Ambiguous capture target.'}
        if($candidates.Count -eq 1) {$game=$candidates[0];break}
        Start-Sleep -Milliseconds 200
    }
    if(!$game) {throw 'Injected game did not start.'}
    $configuration.process_id=$game.Id
    $configuration | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath ($run+'/run.json')
    Write-Host "GPU capture PID $($game.Id): $run"
    while(!$game.HasExited -and $timer.Elapsed.TotalSeconds -lt $DurationSeconds) {
        Start-Sleep -Milliseconds 500;$game.Refresh()
    }
} finally {
    if($game -and !$game.HasExited) {$game.Kill();$game.WaitForExit()}
    $configuration.finished=(Get-Date).ToString('o')
    $configuration | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath ($run+'/run.json')
}
if(!(Test-Path -LiteralPath ($run+'/device_capture.rdc'))) {throw "No capture produced; inspect $run"}
Get-ChildItem -LiteralPath $run | Select-Object Name,Length
