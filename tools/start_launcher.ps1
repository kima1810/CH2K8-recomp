# Preserve startup errors even when opened from the hidden-console shortcut.
$ErrorActionPreference = 'Stop'
try { & (Join-Path $PSScriptRoot 'launch_ch2k8.ps1') }
catch {
    $detail = $_.ToString() + [Environment]::NewLine + $_.ScriptStackTrace
    $log = Join-Path ([IO.Path]::GetTempPath()) 'CH2K8-launcher-startup.log'
    try { [IO.File]::WriteAllText($log, $detail) } catch { }
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show("Launcher could not start. Extract the complete beta ZIP into a writable folder. Details: $log" + [Environment]::NewLine + $_.Exception.Message, 'CH2K8 beta startup') | Out-Null
}
