<#
.SYNOPSIS
Bounded remote GPU-backend experiment with native readbacks and local telemetry.
#>
[CmdletBinding()]
param(
    [ValidateSet('d3d12-rov', 'd3d12-rov-batched', 'd3d12-rtv', 'd3d12-rtv-extent', 'vulkan-fbo', 'vulkan-fsi',
                 'vulkan-fbo-batched', 'vulkan-fsi-batched')]
    [string]$Profile = 'd3d12-rov',
    [ValidateRange(200, 900)][int]$DurationSeconds = 210,
    [string]$Executable,
    [string]$GameData,
    [string]$UserData,
    [ValidateSet('default', 'baseline', 'optimized')][string]$NativeConstants = 'default',
    [ValidateSet('default', 'baseline', 'optimized')][string]$NativePackets = 'default',
    [switch]$GpuStats,
    [switch]$PresentStats,
    [switch]$Visible,
    [ValidateRange(0, 0x7FFFFFFFFFFFFFFF)][long]$CpuAffinityMask = 0,
    [ValidateSet('default','baseline','optimized')][string]$PresentPacing = 'default',
    [switch]$Keyboard,
    [ValidateSet('default','synchronous')][string]$ShaderCompilation = 'default',
    [switch]$ColdShaderCache,
    [switch]$PacketCompare,
    [switch]$HotFunctions,
    [ValidateSet('default','baseline','optimized')][string]$NativeGpuWait = 'default',
    [switch]$GpuWaitStats,
    [ValidateSet('default','baseline','optimized','compare')][string]$GeometryBatch = 'default',
    [ValidateSet('default','baseline','optimized','compare')][string]$RamStore = 'default',
    [ValidateSet('default','baseline','optimized')][string]$PixelState = 'default',
    [ValidateSet('default','baseline','optimized')][string]$DepthState = 'default',
    [ValidateSet('default','baseline','optimized')][string]$FullWrite = 'default',
    [ValidateSet('default','baseline','optimized','compare')][string]$VertexFetch = 'default',
    [ValidateSet('default','baseline','optimized')][string]$GuardedVectorStore = 'default',
    [switch]$ValidateOnly
)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
if (-not $Executable) { $Executable = Join-Path $repoRoot 'port/out/build/win-amd64-vulkan/ch2k8.exe' }
if (-not $GameData) { $GameData = Join-Path $repoRoot 'work/ch2k8/XBOX/disc' }
if (-not $UserData) { $UserData = Join-Path $repoRoot 'port/userdata' }
$Executable = (Resolve-Path -LiteralPath $Executable).Path
$GameData = (Resolve-Path -LiteralPath $GameData).Path
if (-not (Test-Path -LiteralPath $Executable -PathType Leaf)) { throw 'Executable must identify a game build file.' }
if (-not (Test-Path -LiteralPath (Join-Path $GameData 'default.xex') -PathType Leaf)) {
    throw 'GameData must contain the extracted default.xex.'
}
$runRoot = Join-Path $repoRoot ('port/out/render-diagnostics/' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-gpu-' + $Profile)
$backend = if ($Profile.StartsWith('vulkan')) { 'vulkan' } else { 'd3d12' }
$arguments = @('--gpu_plugin=xenos', "--ch2k8_renderer=$backend",
    "--game_data_root=$GameData", "--user_data_root=$UserData",
    '--resolution=1280x720', '--video_mode_refresh_rate=60',
    '--no-fullscreen', '--no-fullscreen_exclusive',
    "--log_file=$(Join-Path $runRoot 'runtime.log')",
    "--ch2k8_frame_log=$(Join-Path $runRoot 'guest-frames.csv')",
    "--ch2k8_output_capture=$(Join-Path $runRoot 'output')",
    '--ch2k8_output_capture_delay=120', '--ch2k8_output_capture_count=2',
    '--ch2k8_output_capture_interval=60')
if ($Profile -like 'd3d12-rtv*') { $arguments += '--render_target_path_d3d12=rtv' }
elseif ($backend -eq 'd3d12') { $arguments += '--render_target_path_d3d12=rov' }
elseif ($Profile -like 'vulkan-fsi*') { $arguments += '--render_target_path_vulkan=fsi' }
else { $arguments += '--render_target_path_vulkan=fbo' }
# Only change the backend's existing primary-buffer submission control. Keep
# explicit waits, coherence/readback controls, and ordering barriers enabled.
if ($Profile.EndsWith('-batched')) { $arguments += "--no-${backend}_submit_on_primary_buffer_end" }
if ($Profile.EndsWith('-extent')) { $arguments += '--execute_unclipped_draw_vs_on_cpu' }
if ($NativeConstants -eq 'baseline') { $arguments += '--no-ch2k8_native_constants' }
elseif ($NativeConstants -eq 'optimized') { $arguments += '--ch2k8_native_constants' }
if ($GpuStats) { $arguments += '--ch2k8_gpu_stats' }
if ($PresentStats) { $arguments += '--ch2k8_present_stats' }
if ($PresentPacing -ne 'default') {
    $arguments += if ($PresentPacing -eq 'baseline') {'--no-ch2k8_native_present_pacing'} else {'--ch2k8_native_present_pacing'}
}
if ($Keyboard) { $arguments += '--mnk_mode' }
if ($ShaderCompilation -eq 'synchronous') { $arguments += '--no-async_shader_compilation' }
if ($ColdShaderCache) { $arguments += '--no-store_shaders' }
if ($PacketCompare) { $arguments += '--ch2k8_packet_compare' }
if ($HotFunctions) { $arguments += "--ch2k8_hot_log=$(Join-Path $runRoot 'hot-functions.csv')" }
if ($NativeGpuWait -ne 'default') { $arguments += if ($NativeGpuWait -eq 'baseline') {'--no-ch2k8_native_gpu_wait'} else {'--ch2k8_native_gpu_wait'} }
if ($GpuWaitStats) { $arguments += '--ch2k8_gpu_wait_stats' }
if ($GeometryBatch -ne 'default') { $arguments += "--ch2k8_geometry_batch=$GeometryBatch" }
if ($RamStore -ne 'default') { $arguments += "--ch2k8_ram_store=$RamStore" }
if ($DepthState -ne 'default') {
    if ($backend -ne 'd3d12') {throw 'DepthState specialization currently requires D3D12.'}
    $arguments += if ($DepthState -eq 'optimized') {'--ch2k8_native_depth_state'} else {'--no-ch2k8_native_depth_state'}
}
if ($GuardedVectorStore -ne 'default') {
    $arguments += if ($GuardedVectorStore -eq 'optimized') {'--ch2k8_guarded_vector_store'} else {'--no-ch2k8_guarded_vector_store'}
}
if ($PixelState -ne 'default') {
    if ($backend -ne 'd3d12') {throw 'PixelState specialization currently requires D3D12.'}
    $arguments += if ($PixelState -eq 'optimized') {'--ch2k8_native_pixel_state'} else {'--no-ch2k8_native_pixel_state'}
}
if ($NativePackets -eq 'baseline') { $arguments += '--no-ch2k8_native_packets' }
elseif ($NativePackets -eq 'optimized') { $arguments += '--ch2k8_native_packets' }
if ($FullWrite -ne 'default') {
    if ($backend -ne 'd3d12') {throw 'FullWrite specialization requires D3D12.'}
    $arguments += if ($FullWrite -eq 'optimized') {'--ch2k8_native_full_write'} else {'--no-ch2k8_native_full_write'}
}
if ($VertexFetch -ne 'default') {
    if ($backend -ne 'd3d12') {throw 'VertexFetch specialization requires D3D12.'}
    $arguments += if ($VertexFetch -eq 'baseline') {'--no-ch2k8_native_vertex_fetch'} else {'--ch2k8_native_vertex_fetch'}
    if ($VertexFetch -eq 'compare') { $arguments += '--ch2k8_vertex_fetch_compare' }
}
foreach ($argument in $arguments) {
    if ($argument.Contains('"')) { throw 'Paths must not contain double quotes.' }
}
$configuration = [ordered]@{
    profile = $Profile; executable = $Executable; arguments = $arguments
    capture_seconds = $DurationSeconds; run_root = $runRoot
    matched_scene = $false
    visible_window = [bool]$Visible
    cpu_affinity_mask = ('0x{0:x}' -f $CpuAffinityMask)
}
if ($ValidateOnly) { $configuration | ConvertTo-Json -Depth 4; return }
if (Get-Process ch2k8 -ErrorAction SilentlyContinue) { throw 'CH2K8 is already running.' }
New-Item -ItemType Directory -Path $runRoot | Out-Null
$configuration.started = (Get-Date).ToString('o')
$configuration.executable_sha256 = (Get-FileHash -LiteralPath $Executable).Hash
$configuration.runtime_binaries_sha256 = @{}
foreach ($binary in (Get-ChildItem -LiteralPath (Split-Path $Executable) -Filter '*.dll' -File)) {
    $configuration.runtime_binaries_sha256[$binary.Name] = (Get-FileHash -LiteralPath $binary.FullName).Hash
}
$game = $null
$telemetry = $null
$writer = $null
$observedAffinity = @{}
$stoppedAtLimit = $false
try {
    $windowStyle = if ($Visible) { 'Normal' } else { 'Hidden' }
    $game = Start-Process -FilePath $Executable -WorkingDirectory (Split-Path $Executable) -ArgumentList ($arguments | ForEach-Object { '"' + $_ + '"' }) -WindowStyle $windowStyle -PassThru
    if ($CpuAffinityMask) { $game.ProcessorAffinity = [IntPtr]$CpuAffinityMask }
    $configuration.process_id = $game.Id
    $configuration | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $runRoot 'run.json') -Encoding utf8
    Write-Host "GPU experiment: $Profile; PID $($game.Id); local output: $runRoot"
    $adl = Join-Path $repoRoot 'work/tooling/adl/amd_telemetry.exe'
    if (Test-Path -LiteralPath $adl) {
        $telemetry = Start-Process -FilePath $adl -ArgumentList @([string]$DurationSeconds) -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runRoot 'amd.csv') -RedirectStandardError (Join-Path $runRoot 'amd-errors.txt') -PassThru
    }
    $writer = [System.IO.StreamWriter]::new((Join-Path $runRoot 'process.csv'), $false)
    $writer.AutoFlush = $true
    $writer.WriteLine('elapsed_s,cpu_time_s,working_set_bytes,threads,cpu_affinity_mask')
    $timer = [System.Diagnostics.Stopwatch]::StartNew()
    while (-not $game.HasExited -and $timer.Elapsed.TotalSeconds -lt $DurationSeconds) {
        $game.Refresh()
        if ($game.HasExited) { break }
        # The SDK initializes its host affinity after process creation. Reapply
        # a diagnostic restriction if that initialization widened the mask.
        if ($CpuAffinityMask -and $game.ProcessorAffinity.ToInt64() -ne $CpuAffinityMask) {
            $game.ProcessorAffinity = [IntPtr]$CpuAffinityMask
        }
        $effectiveAffinity = '0x{0:x}' -f $game.ProcessorAffinity.ToInt64()
        $observedAffinity[$effectiveAffinity] = $true
        $writer.WriteLine(('{0:F3},{1:F3},{2},{3},{4}' -f $timer.Elapsed.TotalSeconds,
            $game.TotalProcessorTime.TotalSeconds, $game.WorkingSet64, $game.Threads.Count, $effectiveAffinity))
        Start-Sleep -Milliseconds 500
    }
    if (-not $game.HasExited) { $stoppedAtLimit = $true; $game.Kill() }
    $game.WaitForExit()
    $configuration.exit_code = $game.ExitCode
} finally {
    if ($writer) { $writer.Dispose() }
    # Stop only children started by this invocation, including on cancellation.
    if ($game -and -not $game.HasExited) { $game.Kill(); $game.WaitForExit() }
    if ($telemetry -and -not $telemetry.HasExited) { $telemetry.Kill(); $telemetry.WaitForExit() }
    $configuration.stopped_at_limit = $stoppedAtLimit
    $configuration.finished = (Get-Date).ToString('o')
    $configuration.observed_cpu_affinity_masks = @($observedAffinity.Keys | Sort-Object)
    $configuration | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $runRoot 'run.json') -Encoding utf8
}
Write-Host 'Compare scene readbacks before interpreting timings. These runs do not lock matchup or camera.'
$python = Join-Path $repoRoot 'port/out/python-env/Scripts/python.exe'
if (Test-Path -LiteralPath $python) {
    & $python (Join-Path $PSScriptRoot 'summarize_gpu_run.py') $runRoot
    if ($LASTEXITCODE) { throw 'GPU run summary failed; raw local outputs were preserved.' }
}
