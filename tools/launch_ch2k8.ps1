<#
.SYNOPSIS
CH2K8 launcher: choose renderer, resolution, refresh rate and window mode.
#>
[CmdletBinding()]
param(
    [ValidateSet('d3d12', 'vulkan')][string]$Renderer = 'd3d12',
    [ValidateSet('auto', 'native', 'accurate')][string]$RenderPath = 'auto',
    [ValidateSet('1280x720', '1600x900', '1920x1080', '2560x1440', '3840x2160')]
    [string]$Resolution = '1280x720',
    [ValidateRange(24, 240)][int]$RefreshRate = 60,
    [ValidateSet('windowed', 'borderless', 'exclusive')][string]$WindowMode = 'windowed',
    [string]$GameData,
    [string]$ImportIso,
    [string]$BuildSource,
    [string]$PythonExecutable,
    [string]$InstallDirectory,
    [string]$Executable,
    [string]$PreviewOutput,
    [switch]$Launch,
    [switch]$CheckSetup,
    [string]$ReportOutput,
    [switch]$ValidateOnly
)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSHOME 'Modules/Microsoft.PowerShell.Utility')
. (Join-Path $PSScriptRoot 'beta_diagnostics.ps1')
$repoRoot = Split-Path -Parent $PSScriptRoot
$settingsPath = Join-Path $repoRoot 'port/userdata/launcher.json'
if (-not $GameData) {
    $GameData = if (Test-Path -LiteralPath (Join-Path $repoRoot 'default.xex')) { $repoRoot }
        elseif (Test-Path -LiteralPath (Join-Path $repoRoot 'game/default.xex')) { Join-Path $repoRoot 'game' }
        else { Join-Path $repoRoot 'work/ch2k8/XBOX/disc' }
}
function ConvertTo-NativeArgument([string]$Value) {
    if ($Value.Contains('"')) { throw 'Paths must not contain double quotes.' }
    # Escape trailing backslashes before the closing native quote.
    return '"' + ($Value -replace '(\\+)$', '$1$1') + '"'
}
function Invoke-Ch2k8SourceBuild {
    param([string]$InputSource, [switch]$Interactive)
    $scriptPath=Join-Path $repoRoot 'tools/build_ch2k8.ps1'
    if (-not (Test-Path -LiteralPath $scriptPath)) { throw 'Source compilation needs the full source checkout. Download it from the beta release page; the runnable ZIP already contains the compiled game.' }
    $job=Join-Path $repoRoot ('port/userdata/builds/'+[guid]::NewGuid().ToString('N'))
    $null=New-Item -ItemType Directory -Path $job -Force
    $arguments=@('-NoProfile','-ExecutionPolicy','Bypass','-File',$scriptPath,'-Source',$InputSource,'-LogFile',(Join-Path $job 'build.log'))
    if ($PythonExecutable) { $arguments+=@('-PythonExecutable',$PythonExecutable) }
    $info=New-Object Diagnostics.ProcessStartInfo
    $info.FileName=Join-Path $PSHOME 'powershell.exe'
    $info.Arguments=($arguments|ForEach-Object{ConvertTo-NativeArgument $_}) -join ' '
    $info.UseShellExecute=$false;$info.CreateNoWindow=$true
    $info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
    $worker=[Diagnostics.Process]::Start($info)
    $stdout=$worker.StandardOutput.ReadToEndAsync();$stderr=$worker.StandardError.ReadToEndAsync()
    try {
        if ($Interactive) {
            $dialog=New-Object System.Windows.Forms.Form
            $dialog.Text='Build recompilation from XEX / ISO'
            $dialog.ClientSize=New-Object Drawing.Size(560,180)
            $dialog.StartPosition='CenterParent';$dialog.FormBorderStyle='FixedDialog';$dialog.ControlBox=$false
            $label=New-Object System.Windows.Forms.Label
            $label.Text="Building the supported USA recompilation. The first build may take 30 minutes or longer. Build prerequisites must be installed. Log: $(Join-Path $job 'build.log')"
            $label.SetBounds(18,18,524,110);$dialog.Controls.Add($label)
            $bar=New-Object System.Windows.Forms.ProgressBar;$bar.Style='Marquee';$bar.SetBounds(18,140,524,20);$dialog.Controls.Add($bar)
            $timer=New-Object System.Windows.Forms.Timer;$timer.Interval=500
            $timer.Add_Tick({
                $progressPath=Join-Path $job 'status.json'
                if(Test-Path -LiteralPath $progressPath){
                    try{
                        $progress=Get-Content -LiteralPath $progressPath -Raw|ConvertFrom-Json
                        $label.Text="Stage: $($progress.stage) ($($progress.state))`r`n$($progress.message)`r`nLog: $(Join-Path $job 'build.log')"
                        if($label.Text.Length -gt 650){$label.Text=$label.Text.Substring(0,650)}
                    }catch{}
                }
                if($worker.HasExited){$timer.Stop();$dialog.Close()}
            })
            try{$timer.Start();$null=$dialog.ShowDialog($form)}finally{$timer.Stop();$timer.Dispose();$dialog.Dispose()}
        }
        $worker.WaitForExit()
        [IO.File]::WriteAllText((Join-Path $job 'stdout.log'),$stdout.GetAwaiter().GetResult())
        $errors=$stderr.GetAwaiter().GetResult();[IO.File]::WriteAllText((Join-Path $job 'stderr.log'),$errors)
        if($worker.ExitCode -ne 0){
            $report=Join-Path $job 'status.json'
            if(Test-Path -LiteralPath $report){
                $failure=Get-Content -LiteralPath $report -Raw|ConvertFrom-Json
                $detail=[string]$failure.message
                if($detail.Length -gt 1400){$detail=$detail.Substring($detail.Length-1400)}
                throw "Build stopped at $($failure.stage).`r`n$detail`r`n$($failure.recovery)`r`nFull log: $(Join-Path $job 'build.log')"
            }
            throw "Source build failed. $errors Build log: $(Join-Path $job 'build.log')"
        }
        return Get-Content -LiteralPath (Join-Path $repoRoot 'port/userdata/build-result.json') -Raw | ConvertFrom-Json
    } finally {$worker.Dispose()}
}
function Get-AssetTool {
    foreach ($candidate in @((Join-Path $repoRoot 'ch2k8_tools.exe'), (Join-Path $repoRoot 'port/out/build/win-amd64-vulkan/ch2k8_tools.exe'), (Join-Path $repoRoot 'port/out/build/win-amd64/ch2k8_tools.exe'), (Join-Path $repoRoot 'out/native-tools/ch2k8_tools.exe'))) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
    }
    throw 'Native asset tools are missing. Extract the complete beta ZIP, or build the ch2k8_tools target from source.'
}

function Import-Ch2k8Iso {
    param([string]$Image, [string]$Destination, [switch]$Interactive)
    if (-not (Test-Path -LiteralPath $Image -PathType Leaf) -or [IO.Path]::GetExtension($Image) -ine '.iso') { throw 'Choose an Xbox 360 ISO file.' }
    if (-not $Destination -or (Test-Path -LiteralPath $Destination)) { throw 'Choose a new installation folder. Existing folders are never overwritten.' }
    $Image = (Resolve-Path -LiteralPath $Image).Path
    $Destination = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Destination)
    $assetTool = Get-AssetTool
    $jobFolder = Join-Path $repoRoot ('port/userdata/imports/' + [guid]::NewGuid().ToString('N'))
    $null = New-Item -ItemType Directory -Path $jobFolder -Force
    $progressFile = Join-Path $jobFolder 'progress.json'
    $cancelFile = Join-Path $jobFolder 'cancel'
    $outputFile = Join-Path $jobFolder 'result.json'
    $errorFile = Join-Path $jobFolder 'import.log'
    $parameters = @('import', $Image, $Destination,
        '--progress-file', $progressFile, '--cancel-file', $cancelFile)
    foreach ($argument in $parameters) { if ($argument.Contains('"')) { throw 'Paths must not contain double quotes.' } }
    $quoted = $parameters | ForEach-Object { ConvertTo-NativeArgument $_ }
    # Start-Process redirection treats brackets in paths as wildcards on PS 5.1.
    # .NET process streams keep Unicode and literal folder names intact.
    $startInfo = New-Object Diagnostics.ProcessStartInfo
    $startInfo.FileName = $assetTool
    $startInfo.Arguments = $quoted -join ' '
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.StandardOutputEncoding = [Text.Encoding]::UTF8
    $startInfo.StandardErrorEncoding = [Text.Encoding]::UTF8
    $worker = New-Object Diagnostics.Process
    $worker.StartInfo = $startInfo
    $null = $worker.Start()
    $stdoutTask = $worker.StandardOutput.ReadToEndAsync()
    $stderrTask = $worker.StandardError.ReadToEndAsync()
    if ($Interactive) {
        $progressDialog = New-Object System.Windows.Forms.Form
        $progressDialog.Text = 'Import Xbox ISO'
        $progressDialog.ClientSize = New-Object System.Drawing.Size(520, 160)
        $progressDialog.StartPosition = 'CenterParent'
        $progressDialog.FormBorderStyle = 'FixedDialog'
        $progressDialog.MaximizeBox = $false
        $progressLabel = New-Object System.Windows.Forms.Label
        $progressLabel.Text = 'Reading ISO. Extraction may take several minutes...'
        $progressLabel.SetBounds(18, 18, 484, 50)
        $progressDialog.Controls.Add($progressLabel)
        $progressBar = New-Object System.Windows.Forms.ProgressBar
        $progressBar.Style = 'Marquee'; $progressBar.SetBounds(18, 75, 484, 20)
        $progressDialog.Controls.Add($progressBar)
        $cancelButton = New-Object System.Windows.Forms.Button
        $cancelButton.Text = 'Cancel'; $cancelButton.SetBounds(402, 112, 100, 30)
        $progressDialog.Controls.Add($cancelButton)
        $cancelButton.Add_Click({ $progressDialog.Close() })
        $progressDialog.Add_FormClosing({
            if (-not $worker.HasExited) {
                $_.Cancel = $true
                [IO.File]::WriteAllText($cancelFile, 'cancel')
                $cancelButton.Enabled = $false
                $progressLabel.Text = 'Cancelling after the current asset operation...'
            }
        })
        $timer = New-Object System.Windows.Forms.Timer
        $timer.Interval = 300
        $timer.Add_Tick({
            if ($worker.HasExited) { $timer.Stop(); $progressDialog.Close(); return }
            if ((Test-Path -LiteralPath $progressFile) -and $cancelButton.Enabled) {
                try {
                    $update = Get-Content -LiteralPath $progressFile -Raw | ConvertFrom-Json
                    $progressLabel.Text = [string]$update.message
                    if ($update.total -gt 0) {
                        $progressBar.Style = 'Continuous'
                        $progressBar.Value = [Math]::Min(100, [int](100 * $update.done / $update.total))
                    }
                } catch { }
            }
        })
        try { $timer.Start(); $null = $progressDialog.ShowDialog($form) }
        finally { $timer.Stop(); $timer.Dispose(); $progressDialog.Dispose() }
    }
    $worker.WaitForExit()
    [IO.File]::WriteAllText($outputFile, $stdoutTask.GetAwaiter().GetResult())
    [IO.File]::WriteAllText($errorFile, $stderrTask.GetAwaiter().GetResult())
    $workerExitCode = $worker.ExitCode
    $worker.Dispose()
    if ($workerExitCode -ne 0) {
        $detail = (Get-Content -LiteralPath $errorFile -Tail 8) -join [Environment]::NewLine
        throw "ISO import failed. $detail"
    }
    $result = Get-Content -LiteralPath $outputFile -Raw | ConvertFrom-Json
    return [string]$result.game_data
}

function Get-LaunchConfiguration {
    param([string]$Backend, [string]$Size, [int]$Hertz, [string]$Mode, [string]$Data, [string]$Program, [string]$Path = 'auto', [switch]$AllowMissing)
    if ($Backend -notin @('d3d12', 'vulkan')) { throw 'Choose a supported renderer.' }
    if ($Path -notin @('auto', 'native', 'accurate')) { throw 'Choose a supported rendering mode.' }
    if ($Size -notmatch '^(1280x720|1600x900|1920x1080|2560x1440|3840x2160)$') {
        throw 'Choose a supported resolution.'
    }
    if ($Hertz -lt 24 -or $Hertz -gt 240) { throw 'Refresh rate must be between 24 and 240 Hz.' }
    if ($Mode -notin @('windowed', 'borderless', 'exclusive')) { throw 'Choose a window mode.' }
    if (-not $Program) {
        $portableBuild = Join-Path $repoRoot 'ch2k8.exe'
        $dualBuild = Join-Path $repoRoot 'port/out/build/win-amd64-vulkan/ch2k8.exe'
        $preset = if ($Backend -eq 'vulkan' -or (Test-Path -LiteralPath $dualBuild)) { 'win-amd64-vulkan' } else { 'win-amd64' }
        $Program = if (Test-Path -LiteralPath $portableBuild -PathType Leaf) { $portableBuild } else { Join-Path $repoRoot "port/out/build/$preset/ch2k8.exe" }
    }
    if (-not $AllowMissing -and -not (Test-Path -LiteralPath $Program -PathType Leaf)) {
        throw "Game build is missing: $Program. This folder has no compiled game. Import ISO extracts assets; it does not compile the source. Use Build from XEX / ISO in the current full source checkout, or download CH2K8-ZMO-beta1-Windows-x64-*.zip under Assets at https://github.com/kima1810/CH2K8-decomp/releases/tag/ZMO-beta1-20261106 (not Source code.zip)."
    }
    if (-not $AllowMissing -and -not (Test-Path -LiteralPath (Join-Path $Data 'default.xex') -PathType Leaf)) {
        throw 'Choose the extracted Xbox 360 game folder containing default.xex.'
    }
    $Program = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Program)
    $Data = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Data)
    $userData = Join-Path $repoRoot 'port/userdata'
    $arguments = @('--gpu_plugin=xenos', "--ch2k8_renderer=$Backend",
        "--game_data_root=$Data", "--user_data_root=$userData",
        "--resolution=$Size", "--video_mode_refresh_rate=$Hertz", '--ch2k8_guest_refresh_rate=60')
    if ($Mode -eq 'windowed') { $arguments += @('--no-fullscreen', '--no-fullscreen_exclusive') }
    elseif ($Mode -eq 'exclusive') { $arguments += @('--fullscreen', '--fullscreen_exclusive') }
    else { $arguments += @('--fullscreen', '--no-fullscreen_exclusive') }
    if ($Backend -eq 'd3d12') {
        $target = if ($Path -eq 'accurate') { 'rov' } else { 'rtv' }
        $arguments += "--render_target_path_d3d12=$target"
        if ($target -eq 'rtv') {
            $arguments += @('--execute_unclipped_draw_vs_on_cpu', '--no-async_shader_compilation')
        }
    } else {
        $target = if ($Path -eq 'native') { 'fbo' } else { 'fsi' }
        $arguments += "--render_target_path_vulkan=$target"
    }
    # Native process arguments need quoting for paths containing spaces;
    # quote each complete argument and reject embedded native quote characters.
    foreach ($argument in $arguments) {
        if ($argument.Contains('"')) { throw 'Paths must not contain double quotes.' }
    }
    [pscustomobject]@{ executable = $Program; arguments = $arguments }
}

function Invoke-Ch2k8Preparation {
    param([string]$AssetRoot, [switch]$Interactive)
    $assetTool = Get-AssetTool
    $info = New-Object Diagnostics.ProcessStartInfo
    $info.FileName = $assetTool
    $info.Arguments = (@('prepare', $AssetRoot) | ForEach-Object { ConvertTo-NativeArgument $_ }) -join ' '
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    $info.StandardOutputEncoding = [Text.Encoding]::UTF8
    $info.StandardErrorEncoding = [Text.Encoding]::UTF8
    $worker = [Diagnostics.Process]::Start($info)
    $stdoutTask = $worker.StandardOutput.ReadToEndAsync()
    $stderrTask = $worker.StandardError.ReadToEndAsync()
    try {
        if ($Interactive) {
            $dialog = New-Object System.Windows.Forms.Form
            $dialog.Text = 'Preparing game assets'
            $dialog.ClientSize = New-Object System.Drawing.Size(480, 130)
            $dialog.StartPosition = 'CenterParent'
            $dialog.FormBorderStyle = 'FixedDialog'
            $dialog.ControlBox = $false
            $label = New-Object System.Windows.Forms.Label
            $label.Text = 'Validating folder assets before play. This can take several minutes. The game will start when preparation finishes.'
            $label.SetBounds(18, 16, 444, 65)
            $dialog.Controls.Add($label)
            $bar = New-Object System.Windows.Forms.ProgressBar
            $bar.Style = 'Marquee'; $bar.SetBounds(18, 90, 444, 20)
            $dialog.Controls.Add($bar)
            $timer = New-Object System.Windows.Forms.Timer
            $timer.Interval = 250
            $timer.Add_Tick({ if ($worker.HasExited) { $timer.Stop(); $dialog.Close() } })
            try { $timer.Start(); $null = $dialog.ShowDialog($form) }
            finally { $timer.Stop(); $timer.Dispose(); $dialog.Dispose() }
        }
        $worker.WaitForExit()
        $output = $stdoutTask.GetAwaiter().GetResult()
        $errors = $stderrTask.GetAwaiter().GetResult()
        if ($worker.ExitCode -ne 0) { throw ('Loose asset validation failed. The game was not started. ' + $errors + $output) }
    } finally { $worker.Dispose() }
}

function Start-Ch2k8 {
    param($Configuration, [switch]$Background)
    $setup = Test-BetaEnvironment $Configuration
    if (-not $setup.ready) { throw ($setup.failures -join [Environment]::NewLine) }
    if (Get-Process ch2k8 -ErrorAction SilentlyContinue) { throw 'CH2K8 is already running.' }
    $rootArgument = $Configuration.arguments | Where-Object { $_.StartsWith('--game_data_root=') }
    $assetRoot = $rootArgument.Substring('--game_data_root='.Length)
    if (Test-Path -LiteralPath (Join-Path $assetRoot 'assets.json')) {
        if ($Configuration.arguments -contains '--ch2k8_renderer=vulkan') {
            throw 'Native DDS replacement currently requires Direct3D 12. Choose D3D12 for the folder installation.'
        }
        Invoke-Ch2k8Preparation $assetRoot -Interactive:([bool]($form -and $form.Visible -and -not $Background))
    }
    $logRoot = Join-Path (Split-Path -Parent $Configuration.executable) 'logs'
    $null = New-Item -ItemType Directory -Path $logRoot -Force
    $logFile = Join-Path $logRoot ('ch2k8-' + [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss-ffff') + '.log')
    $launchArguments = @($Configuration.arguments) + "--log_file=$logFile"
    $null = New-Item -ItemType Directory -Path (Split-Path -Parent $settingsPath) -Force
    @{ attempted_utc=[DateTime]::UtcNow.ToString('o'); arguments=$launchArguments } | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path (Split-Path -Parent $settingsPath) 'last-launch.json') -Encoding UTF8
    $nativeArguments = $launchArguments | ForEach-Object { ConvertTo-NativeArgument $_ }
    $startInfo = New-Object Diagnostics.ProcessStartInfo
    $startInfo.FileName = $Configuration.executable
    $startInfo.WorkingDirectory = Split-Path -Parent $Configuration.executable
    $startInfo.Arguments = $nativeArguments -join ' '
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = [bool]$Background
    $startInfo.WindowStyle = if ($Background) { 'Hidden' } else { 'Normal' }
    return [Diagnostics.Process]::Start($startInfo)
}

if ($BuildSource) {
    if ($ValidateOnly) {
        & (Join-Path $repoRoot 'tools/build_ch2k8.ps1') -Source $BuildSource -PythonExecutable $PythonExecutable -ValidateOnly
        return
    }
    $result=Invoke-Ch2k8SourceBuild $BuildSource
    $result|ConvertTo-Json
    return
}
if ($ImportIso) {
    if ($ValidateOnly) { throw 'Use ImportIso without ValidateOnly to extract a new loose installation.' }
    $GameData = Import-Ch2k8Iso $ImportIso $InstallDirectory
    if (-not $Launch) { @{ game_data = $GameData; storage = 'loose-resources' } | ConvertTo-Json; return }
}
if ($CheckSetup -or $ReportOutput) {
    $configuration = Get-LaunchConfiguration $Renderer $Resolution $RefreshRate $WindowMode $GameData $Executable $RenderPath -AllowMissing
    $setup = Test-BetaEnvironment $configuration
    if ($ReportOutput) { Export-BetaReport $ReportOutput $configuration $setup }
    else { $setup | ConvertTo-Json -Depth 4 }
    if (-not $setup.ready) { exit 1 }
    return
}
if ($Launch -or $ValidateOnly) {
    $configuration = Get-LaunchConfiguration $Renderer $Resolution $RefreshRate $WindowMode $GameData $Executable $RenderPath
    if ($ValidateOnly) { $configuration | ConvertTo-Json -Depth 3 }
    else { Start-Ch2k8 $configuration | Select-Object Id }
    return
}

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()
try {
    if (Test-Path -LiteralPath $settingsPath) {
        $saved = Get-Content -LiteralPath $settingsPath -Raw | ConvertFrom-Json
        if (-not $PSBoundParameters.ContainsKey('Renderer') -and $saved.renderer -in @('d3d12', 'vulkan')) { $Renderer = $saved.renderer }
        if (-not $PSBoundParameters.ContainsKey('RenderPath') -and $saved.render_path -in @('auto', 'native', 'accurate')) { $RenderPath = $saved.render_path }
        if (-not $PSBoundParameters.ContainsKey('Resolution') -and $saved.resolution -match '^(1280x720|1600x900|1920x1080|2560x1440|3840x2160)$') { $Resolution = $saved.resolution }
        if (-not $PSBoundParameters.ContainsKey('RefreshRate') -and $saved.refresh_rate -ge 24 -and $saved.refresh_rate -le 240) { $RefreshRate = [int]$saved.refresh_rate }
        if (-not $PSBoundParameters.ContainsKey('WindowMode') -and $saved.window_mode -in @('windowed', 'borderless', 'exclusive')) { $WindowMode = $saved.window_mode }
        if (-not $PSBoundParameters.ContainsKey('GameData') -and $saved.game_data) { $GameData = [string]$saved.game_data }
        if (-not $PSBoundParameters.ContainsKey('Executable') -and $saved.executable -and (Test-Path -LiteralPath (Join-Path $repoRoot 'port/ch2k8_manifest.toml')) -and (Test-Path -LiteralPath $saved.executable -PathType Leaf)) { $Executable=[string]$saved.executable }
    }
} catch { Write-Verbose "Ignoring invalid launcher settings: $_" }

$form = New-Object System.Windows.Forms.Form
$form.Text = 'College Hoops 2K8 - ZMO beta 1'
$form.ClientSize = New-Object System.Drawing.Size(620, 755)
$form.StartPosition = 'CenterScreen'
$form.FormBorderStyle = 'FixedDialog'
$form.MaximizeBox = $false
$form.Font = New-Object System.Drawing.Font('Segoe UI', 10)
$form.BackColor = [System.Drawing.Color]::FromArgb(24, 28, 35)
$form.ForeColor = [System.Drawing.Color]::WhiteSmoke
$form.AutoScaleMode = 'Dpi'
$form.AutoScroll = $true
$form.Add_Shown({
    $area = [System.Windows.Forms.Screen]::FromControl($form).WorkingArea
    # Keep every control reachable on small screens and high-DPI desktops.
    if ($form.Height -gt $area.Height) { $form.Height = $area.Height }
    if ($form.Width -gt $area.Width) { $form.Width = $area.Width }
})

function Add-Label([string]$Text, [int]$X, [int]$Y, [int]$Width = 260) {
    $label = New-Object System.Windows.Forms.Label
    $label.Text = $Text
    $label.Location = New-Object System.Drawing.Point($X, $Y)
    $label.Size = New-Object System.Drawing.Size($Width, 24)
    $form.Controls.Add($label)
    return $label
}
function Add-Choice([string[]]$Items, [int]$X, [int]$Y, [int]$Width = 260) {
    $choice = New-Object System.Windows.Forms.ComboBox
    $choice.DropDownStyle = 'DropDownList'
    $choice.Location = New-Object System.Drawing.Point($X, $Y)
    $choice.Size = New-Object System.Drawing.Size($Width, 30)
    $choice.Items.AddRange([object[]]$Items)
    $form.Controls.Add($choice)
    return $choice
}
$title = Add-Label 'COLLEGE HOOPS 2K8' 24 20 560
$title.Font = New-Object System.Drawing.Font('Segoe UI', 19, [System.Drawing.FontStyle]::Bold)
$title.Height = 40
$null = Add-Label 'Renderer' 24 80
$backend = Add-Choice @('Direct3D 12', 'Vulkan (experimental)') 24 106
$backend.SelectedIndex = if ($Renderer -eq 'vulkan') { 1 } else { 0 }
$null = Add-Label 'Window mode' 326 80
$mode = Add-Choice @('Windowed', 'Borderless fullscreen', 'Exclusive fullscreen') 326 106
$mode.SelectedIndex = @('windowed', 'borderless', 'exclusive').IndexOf($WindowMode)
$null = Add-Label 'Resolution' 24 155
$size = Add-Choice @('1280x720', '1600x900', '1920x1080', '2560x1440', '3840x2160') 24 181
$size.SelectedItem = $Resolution
$null = Add-Label 'Refresh rate (Hz)' 326 155
$rate = New-Object System.Windows.Forms.NumericUpDown
$rate.Minimum = 24; $rate.Maximum = 240; $rate.Value = $RefreshRate
$rate.Location = New-Object System.Drawing.Point(326, 181)
$rate.Size = New-Object System.Drawing.Size(260, 30)
$form.Controls.Add($rate)
$null = Add-Label 'Rendering mode' 24 229 560
$renderMode = Add-Choice @('Automatic', 'Native render targets', 'Accurate Xbox blending') 24 255 562
$renderMode.SelectedIndex = @('auto', 'native', 'accurate').IndexOf($RenderPath)
$hint = Add-Label 'Automatic uses tested native D3D12 rendering. Accurate Xbox blending is the compatibility fallback; Vulkan native targets remain experimental.' 24 296 570
$hint.ForeColor = [System.Drawing.Color]::Silver
$hint.Height = 40
$null = Add-Label 'Game folder (or import your Xbox ISO below)' 24 344 560
$dataBox = New-Object System.Windows.Forms.TextBox
$dataBox.Text = $GameData
$dataBox.Location = New-Object System.Drawing.Point(24, 370)
$dataBox.Size = New-Object System.Drawing.Size(466, 30)
$form.Controls.Add($dataBox)
$browse = New-Object System.Windows.Forms.Button
$browse.Text = 'Browse...'
$browse.Location = New-Object System.Drawing.Point(500, 368)
$browse.Size = New-Object System.Drawing.Size(86, 32)
$form.Controls.Add($browse)
$browse.Add_Click({
    $dialog = New-Object System.Windows.Forms.FolderBrowserDialog
    $dialog.Description = 'Select the extracted Xbox 360 disc folder containing default.xex'
    $dialog.SelectedPath = $dataBox.Text
    if ($dialog.ShowDialog($form) -eq 'OK') { $dataBox.Text = $dialog.SelectedPath }
    $dialog.Dispose()
})
$import = New-Object System.Windows.Forms.Button
$import.Text = 'Import ISO...'
$import.SetBounds(24, 410, 170, 34)
$form.Controls.Add($import)
$importHint = Add-Label 'Uses native tools. No Python needed for ISO import.' 395 414 195
$selectXex=New-Object System.Windows.Forms.Button
$selectXex.Text='Select XEX...'
$selectXex.SetBounds(208,410,170,34);$form.Controls.Add($selectXex)
$selectXex.Add_Click({
    $dialog=New-Object System.Windows.Forms.OpenFileDialog
    $dialog.Filter='Xbox 360 executable (*.xex)|*.xex'
    try {
        if($dialog.ShowDialog($form) -eq 'OK'){
            if((Get-FileHash -LiteralPath $dialog.FileName).Hash.ToLowerInvariant() -ne '71e8983d1cc009e485696aad19b5fa4b4661761870e2c8972717b932c1e4be36'){throw 'Select the original USA College Hoops 2K8 default.xex.'}
            $dataBox.Text=Split-Path -Parent $dialog.FileName
            $status.Text='XEX selected. Playing also needs the disc assets beside default.xex. Use Import ISO if you have the full ISO.'
        }
    }catch{$status.Text=$_.Exception.Message}finally{$dialog.Dispose()}
})
$importHint.Height = 42
$importHint.ForeColor = [System.Drawing.Color]::Silver
$import.Add_Click({
    $imageDialog = New-Object System.Windows.Forms.OpenFileDialog
    $imageDialog.Title = 'Select your USA Xbox 360 College Hoops 2K8 ISO'
    $imageDialog.Filter = 'Xbox 360 ISO (*.iso)|*.iso'
    $destinationDialog = New-Object System.Windows.Forms.FolderBrowserDialog
    try {
        if ($imageDialog.ShowDialog($form) -ne 'OK') { return }
        $folderName = [IO.Path]::GetFileNameWithoutExtension($imageDialog.FileName) + '-assets'
        $destinationDialog.Description = "Choose where to create the new $folderName installation folder"
        if ($destinationDialog.ShowDialog($form) -ne 'OK') { return }
        $destination = Join-Path $destinationDialog.SelectedPath $folderName
        $dataBox.Text = Import-Ch2k8Iso $imageDialog.FileName $destination -Interactive
        $backend.SelectedIndex = 0
        $null = New-Item -ItemType Directory -Path (Split-Path -Parent $settingsPath) -Force
        # Preserve the display settings until Launch saves the full selection.
        $savedSettings = @{}
        if (Test-Path -LiteralPath $settingsPath) {
            try { (Get-Content -LiteralPath $settingsPath -Raw | ConvertFrom-Json).PSObject.Properties | ForEach-Object { $savedSettings[$_.Name] = $_.Value } } catch { }
        }
        $savedSettings.game_data = $dataBox.Text
        $savedSettings.renderer = 'd3d12'
        $savedSettings | ConvertTo-Json | Set-Content -LiteralPath $settingsPath -Encoding utf8
        $status.Text = 'ISO imported as loose assets. The original ISO is unchanged. Check setup, then launch.'
    } catch { [System.Windows.Forms.MessageBox]::Show($form, $_.Exception.Message, 'ISO import', 'OK', 'Error') | Out-Null }
    finally { $imageDialog.Dispose(); $destinationDialog.Dispose() }
})
$play = New-Object System.Windows.Forms.Button
$play.Text = 'Launch game'
$play.Location = New-Object System.Drawing.Point(392, 588)
$play.Size = New-Object System.Drawing.Size(194, 46)
$play.FlatStyle = 'Flat'
$play.BackColor = [System.Drawing.Color]::FromArgb(164, 43, 49)
$form.Controls.Add($play)
$status = Add-Label 'Browse to a game folder or import an ISO, then check setup.' 24 464 562
$status.Height = 62
$status.ForeColor = [System.Drawing.Color]::Silver
$check = New-Object System.Windows.Forms.Button
$check.Text = 'Check setup'
$check.Location = New-Object System.Drawing.Point(24, 536)
$check.Size = New-Object System.Drawing.Size(170, 34)
$form.Controls.Add($check)
$check.Add_Click({
    try {
        $configuration = Get-LaunchConfiguration @('d3d12', 'vulkan')[$backend.SelectedIndex] ([string]$size.SelectedItem) ([int]$rate.Value) @('windowed', 'borderless', 'exclusive')[$mode.SelectedIndex] $dataBox.Text $Executable @('auto', 'native', 'accurate')[$renderMode.SelectedIndex]
        $setup = Test-BetaEnvironment $configuration
        if (-not $setup.ready) { throw ($setup.failures -join ' ') }
        $status.Text = 'Preflight passed. Launch validates folder edits. GPU gameplay compatibility still needs testing.'
    } catch { $status.Text = $_.Exception.Message }
})
$files = New-Object System.Windows.Forms.Button
$files.Text = 'Saves / settings'
$files.Location = New-Object System.Drawing.Point(210, 536)
$files.Size = New-Object System.Drawing.Size(170, 34)
$form.Controls.Add($files)
$files.Add_Click({
    try {
        $folder = Join-Path $repoRoot 'port/userdata'
        $null = New-Item -ItemType Directory -Path $folder -Force
        Start-Process explorer.exe -ArgumentList ('"' + $folder + '"')
    } catch { $status.Text = $_.Exception.Message }
})
$logs = New-Object System.Windows.Forms.Button
$logs.Text = 'Open logs'
$logs.Location = New-Object System.Drawing.Point(396, 536)
$logs.Size = New-Object System.Drawing.Size(190, 34)
$form.Controls.Add($logs)
$logs.Add_Click({
    try {
        $configuration = Get-LaunchConfiguration @('d3d12', 'vulkan')[$backend.SelectedIndex] ([string]$size.SelectedItem) ([int]$rate.Value) @('windowed', 'borderless', 'exclusive')[$mode.SelectedIndex] $dataBox.Text $Executable
        $folder = Join-Path (Split-Path -Parent $configuration.executable) 'logs'
        $null = New-Item -ItemType Directory -Path $folder -Force
        Start-Process explorer.exe -ArgumentList ('"' + $folder + '"')
    } catch { $status.Text = $_.Exception.Message }
})
$reportButton = New-Object System.Windows.Forms.Button
$reportButton.Text = 'Export bug report'
$reportButton.SetBounds(24, 588, 220, 46)
$form.Controls.Add($reportButton)
$reportButton.Add_Click({
    $dialog = New-Object System.Windows.Forms.SaveFileDialog
    $dialog.Filter = 'Bug report ZIP (*.zip)|*.zip'
    $dialog.FileName = 'CH2K8-beta-report-' + [DateTime]::Now.ToString('yyyyMMdd-HHmmss') + '.zip'
    try {
        if ($dialog.ShowDialog($form) -ne 'OK') { return }
        $configuration = Get-LaunchConfiguration @('d3d12', 'vulkan')[$backend.SelectedIndex] ([string]$size.SelectedItem) ([int]$rate.Value) @('windowed', 'borderless', 'exclusive')[$mode.SelectedIndex] $dataBox.Text $Executable @('auto', 'native', 'accurate')[$renderMode.SelectedIndex] -AllowMissing
        $setup = Test-BetaEnvironment $configuration
        $path = Export-BetaReport $dialog.FileName $configuration $setup
        $status.Text = 'Report saved. Review the ZIP, add reproduction steps, then share it with the beta report.'
    } catch { $status.Text = $_.Exception.Message }
    finally { $dialog.Dispose() }
})
$buildButton=New-Object System.Windows.Forms.Button
$buildButton.Text='Build from XEX / ISO'
$buildButton.SetBounds(24,648,265,36)
$buildButton.Enabled=(Test-Path -LiteralPath (Join-Path $repoRoot 'port/ch2k8_manifest.toml')) -and (Test-Path -LiteralPath (Join-Path $repoRoot 'tools/build_ch2k8.ps1'))
$form.Controls.Add($buildButton)
$buildButton.Add_Click({
    $dialog=New-Object System.Windows.Forms.OpenFileDialog
    $dialog.Filter='College Hoops 2K8 executable or disc (*.xex;*.iso)|*.xex;*.iso'
    try{
        if($dialog.ShowDialog($form) -ne 'OK'){return}
        $result=Invoke-Ch2k8SourceBuild $dialog.FileName -Interactive
        $script:Executable=[string]$result.executable
        if($result.game_data){$dataBox.Text=[string]$result.game_data}
        $status.Text=if($result.data_ready){'Build completed. Check setup, then launch.'}else{'Recompilation built. Select a complete disc folder or import an ISO before playing; a bare XEX has no game assets.'}
    }catch{[System.Windows.Forms.MessageBox]::Show($form,$_.Exception.Message,'Source build','OK','Error')|Out-Null}finally{$dialog.Dispose()}
})
$download=New-Object System.Windows.Forms.Button
$download.Text='Download runnable beta'
$download.SetBounds(312,648,274,36);$form.Controls.Add($download)
$download.Add_Click({Start-Process 'https://github.com/kima1810/CH2K8-decomp/releases/tag/ZMO-beta1-20261106'})
$distributionHint=Add-Label 'GitHub source ZIPs require compilation. The release asset includes ch2k8.exe and all runtime files.' 24 700 562
$distributionHint.Height=42;$distributionHint.ForeColor=[Drawing.Color]::Silver
if(-not (Test-Path -LiteralPath (Join-Path $repoRoot 'ch2k8.exe')) -and -not (Test-Path -LiteralPath (Join-Path $repoRoot 'port/out/build/win-amd64-vulkan/ch2k8.exe')) -and -not (Test-Path -LiteralPath (Join-Path $repoRoot 'port/out/build/win-amd64/ch2k8.exe'))){$status.Text='Source checkout: build from XEX / ISO, or download the runnable beta below. An ISO import alone does not compile the game.'}
$form.AcceptButton = $play
$play.Add_Click({
    try {
        $selectedBackend = @('d3d12', 'vulkan')[$backend.SelectedIndex]
        $selectedMode = @('windowed', 'borderless', 'exclusive')[$mode.SelectedIndex]
        $selectedPath = @('auto', 'native', 'accurate')[$renderMode.SelectedIndex]
        $configuration = Get-LaunchConfiguration $selectedBackend ([string]$size.SelectedItem) ([int]$rate.Value) $selectedMode $dataBox.Text $Executable $selectedPath
        $null = Start-Ch2k8 $configuration
        $null = New-Item -ItemType Directory -Path (Split-Path -Parent $settingsPath) -Force
        @{ renderer = $selectedBackend; render_path = $selectedPath; resolution = [string]$size.SelectedItem;
           refresh_rate = [int]$rate.Value; window_mode = $selectedMode;
           game_data = $dataBox.Text; executable = $configuration.executable } | ConvertTo-Json | Set-Content -LiteralPath $settingsPath -Encoding utf8
        $form.Close()
    } catch {
        [System.Windows.Forms.MessageBox]::Show($form, $_.Exception.Message, 'Unable to launch', 'OK', 'Error') | Out-Null
    }
})
if ($PreviewOutput) {
    $form.Show()
    [System.Windows.Forms.Application]::DoEvents()
    $check.PerformClick()
    $form.Refresh()
    $bitmap = New-Object System.Drawing.Bitmap($form.Width, $form.Height)
    $form.DrawToBitmap($bitmap, (New-Object System.Drawing.Rectangle(0, 0, $form.Width, $form.Height)))
    $bitmap.Save([System.IO.Path]::GetFullPath($PreviewOutput), [System.Drawing.Imaging.ImageFormat]::Png)
    $bitmap.Dispose()
} else {
    $null = $form.ShowDialog()
}
$form.Dispose()
