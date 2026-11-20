[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$InstallationRoot,[Parameter(Mandatory=$true)][string]$CurrentRuntime,[Parameter(Mandatory=$true)][string]$Job,[switch]$Rollback)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'chmod.ps1')
. (Join-Path $PSScriptRoot 'runtime_update.ps1')
try{
    $root=[IO.Path]::GetFullPath($InstallationRoot)
    $expected=Get-ModPath (Get-Ch2k8UpdateState $root) ('jobs/'+[IO.Path]::GetFileName($Job))
    if([IO.Path]::GetFullPath($Job) -ine $expected -or [IO.Path]::GetFileName($Job) -cnotmatch '^[0-9a-f]{32}$'){throw 'Invalid updater job directory.'}
    $message=Install-Ch2k8LatestRuntime $root $CurrentRuntime $Job -Rollback:$Rollback
    Write-Ch2k8UpdateStatus $Job 'Complete' $message $true $true
}catch{
    Write-Ch2k8UpdateStatus $Job 'Stopped' $_.Exception.Message $true $false
    exit 1
}
