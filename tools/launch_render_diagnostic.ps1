<#
.SYNOPSIS
Run one CH2K8 rendering comparison and preserve its settings and CPU samples.
#>
[CmdletBinding()]
param(
    [ValidateSet('baseline', 'rov', 'rov-ui', 'synchronous', 'vulkan', 'vulkan-fsi')]
    [string]$Profile = 'rov',
    [string]$Executable,
    [string]$GameData,
    [string]$UserData,
    [string]$PresentMon,
    [ValidateRange(10, 3600)]
    [int]$CaptureSeconds = 600
)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
if (-not $Executable) {
    $preset = if ($Profile -like 'vulkan*') { 'win-amd64-vulkan' } else { 'win-amd64' }
    $Executable = Join-Path $repoRoot "port/out/build/$preset/ch2k8.exe"
}
if (-not $GameData) { $GameData = Join-Path $repoRoot 'work/ch2k8/XBOX/disc' }
if (-not $UserData) { $UserData = Join-Path $repoRoot 'port/userdata' }
if (-not $PresentMon) { $PresentMon = Join-Path $repoRoot 'work/tooling/presentmon/PresentMon-2.6.0-x64.exe' }
$Executable = (Resolve-Path -LiteralPath $Executable).Path
$GameData = (Resolve-Path -LiteralPath $GameData).Path
if (-not (Test-Path -LiteralPath (Join-Path $GameData 'default.xex'))) {
    throw "Extracted game data is missing default.xex: $GameData"
}
if (Get-Process ch2k8 -ErrorAction SilentlyContinue) {
    throw 'Close the running CH2K8 instance before starting a rendering comparison.'
}
$runRoot = Join-Path $repoRoot ('port/out/render-diagnostics/' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + $Profile)
New-Item -ItemType Directory -Path $runRoot -Force | Out-Null
$runtimeLog = Join-Path $runRoot 'runtime.log'
$performanceLog = Join-Path $runRoot 'process.csv'
$arguments = @(
    "--game_data_root=$GameData", '--gpu_plugin=xenos',
    "--user_data_root=$UserData", "--log_file=$runtimeLog",
    "--ch2k8_frame_log=$(Join-Path $runRoot 'guest-frames.csv')"
)
switch ($Profile) {
    'rov' { $arguments += '--render_target_path_d3d12=rov' }
    'rov-ui' { $arguments += '--render_target_path_d3d12=rov'; $arguments += '--no-host_present_from_non_ui_thread' }
    'synchronous' { $arguments += '--no-async_shader_compilation' }
    'vulkan' { $arguments += '--ch2k8_renderer=vulkan' }
    'vulkan-fsi' { $arguments += @('--ch2k8_renderer=vulkan', '--render_target_path_vulkan=fsi') }
}
@{
    profile = $Profile
    started = (Get-Date).ToString('o')
    executable = $Executable
    executable_sha256 = (Get-FileHash -LiteralPath $Executable -Algorithm SHA256).Hash
    arguments = $arguments
    presentmon = $PresentMon
    capture_seconds = $CaptureSeconds
} | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath (Join-Path $runRoot 'run.json') -Encoding utf8
Write-Host "Rendering comparison: $Profile"
Write-Host "Logs: $runRoot"
Write-Host 'Use the same matchup and camera. Observe live play, pause, then replay.'
Write-Host 'Close the game normally when finished.'
# Start-Process joins its argument array into one native command line. Quote
# each complete argument because the game and user-data paths contain spaces.
$nativeArguments = $arguments | ForEach-Object { '"' + $_ + '"' }
$gameProcess = Start-Process -FilePath $Executable -WorkingDirectory (Split-Path -Parent $Executable) -ArgumentList $nativeArguments -WindowStyle Normal -PassThru
$traceProcess = $null
$traceSession = 'CH2K8-' + $gameProcess.Id
if (Test-Path -LiteralPath $PresentMon) {
    $traceArguments = @('--process_id', $gameProcess.Id, '--output_file', ('"'+(Join-Path $runRoot 'presentmon.csv')+'"'), '--session_name', $traceSession, '--terminate_on_proc_exit', '--timed', $CaptureSeconds, '--terminate_after_timed', '--no_console_stats', '--no_track_input')
    $traceProcess = Start-Process -FilePath $PresentMon -ArgumentList $traceArguments -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runRoot 'presentmon-stdout.txt') -RedirectStandardError (Join-Path $runRoot 'presentmon-stderr.txt') -PassThru
    @{ process_id = $traceProcess.Id; session = $traceSession; game_process_id = $gameProcess.Id } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runRoot 'trace.json') -Encoding utf8
    if ($traceProcess.WaitForExit(300) -and $traceProcess.ExitCode -ne 0) {
        Write-Warning ('PresentMon could not start; inspect presentmon-stderr.txt. ETW access may require running this diagnostic as administrator. CPU sampling will continue.')
    } else {
        Write-Host 'PresentMon started (presentation calls are not gameplay FPS); check its stderr log for capture errors.'
    }
} else {
    Write-Host 'PresentMon is unavailable; recording process samples only.'
}
$timer = [System.Diagnostics.Stopwatch]::StartNew()
$previousCpu = 0.0
$writer = [System.IO.StreamWriter]::new($performanceLog, $false)
$writer.AutoFlush = $true
$writer.WriteLine('elapsed_s,cpu_time_s,cpu_delta_ms,working_set_bytes,threads')
try {
    while (-not $gameProcess.HasExited) {
        try {
            $gameProcess.Refresh()
            $cpu = $gameProcess.TotalProcessorTime.TotalSeconds
            $row = '{0:F3},{1:F3},{2:F3},{3},{4}' -f $timer.Elapsed.TotalSeconds, $cpu, (($cpu-$previousCpu)*1000), $gameProcess.WorkingSet64, $gameProcess.Threads.Count
            $writer.WriteLine($row)
            $previousCpu = $cpu
        } catch [System.InvalidOperationException] {
            if (-not $gameProcess.HasExited) { throw }
        }
        Start-Sleep -Milliseconds 500
    }
    $gameProcess.WaitForExit()
    $gameExitCode = $gameProcess.ExitCode
} finally {
    $writer.Dispose()
    if ($traceProcess -and -not $traceProcess.WaitForExit(5000)) {
        # End only the session created by this launcher, preserving other traces.
        $stopTrace = Start-Process -FilePath $PresentMon -ArgumentList @('--session_name',$traceSession,'--terminate_existing_session') -WindowStyle Hidden -PassThru
        $stopTrace.WaitForExit(5000) | Out-Null
        if (-not $traceProcess.WaitForExit(5000)) {
            Write-Warning ('PresentMon is still flushing; its independent timer will end capture. Session: '+$traceSession)
        }
    }
}
Write-Host "Game exited with code $gameExitCode. Logs: $runRoot"
