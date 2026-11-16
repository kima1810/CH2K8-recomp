# Preserve startup errors even when opened from the hidden-console shortcut.
$ErrorActionPreference = 'Stop'
try {
    $installation=Split-Path -Parent $PSScriptRoot
    . (Join-Path $PSScriptRoot 'chmod.ps1')
    . (Join-Path $PSScriptRoot 'runtime_update.ps1')
    $active=$installation
    try{$active=Get-Ch2k8ActiveRuntime $installation}catch{
        Add-Type -AssemblyName System.Windows.Forms
        [System.Windows.Forms.MessageBox]::Show(('The selected update could not be verified. Opening the original launcher for recovery. Use Rollback update.'+[Environment]::NewLine+$_.Exception.Message),'CH2K8 update recovery')|Out-Null
    }
    & (Join-Path $active 'tools/launch_ch2k8.ps1') -InstallationRoot $installation
}catch{
    $detail=$_.ToString()+[Environment]::NewLine+$_.ScriptStackTrace
    $log=Join-Path ([IO.Path]::GetTempPath()) 'CH2K8-launcher-startup.log'
    try{[IO.File]::WriteAllText($log,$detail)}catch{}
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show("Launcher could not start. Details: $log"+[Environment]::NewLine+$_.Exception.Message,'CH2K8 startup')|Out-Null
}
