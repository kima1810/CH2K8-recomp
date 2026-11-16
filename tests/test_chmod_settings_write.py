"""Prepared Windows PowerShell regression; not executed by the agent.

Uses only pytest temporary settings files, never user preferences or saves.
"""
from test_chmod import ps

def test_existing_settings_atomic_replace_and_stale_hash(tmp_path):
    ps(tmp_path, r'''
$file=Join-Path $args[1] 'mods.json'
Write-ModJson $file ([ordered]@{version=1;enabled=@();allow_native_code=$false})
$original=Get-ModHash $file
$selected=@([pscustomobject]@{id='test.mod';version='1.0.0'})
Write-ModJson $file ([ordered]@{version=1;enabled=$selected;allow_native_code=$true}) $original
$saved=Read-ModJson $file
if($saved.enabled.Count -ne 1 -or $saved.enabled[0].id -cne 'test.mod' -or $saved.allow_native_code -ne $true){throw 'Existing settings were not replaced'}
$current=Get-ModHash $file
$rejected=$false
try{Write-ModJson $file ([ordered]@{version=1;enabled=@();allow_native_code=$false}) $original}catch{$rejected=$true}
if(-not $rejected -or (Get-ModHash $file) -cne $current){throw 'Stale settings update changed the committed selection'}
Write-ModJson $file ([ordered]@{version=1;enabled=@();allow_native_code=$true}) $current
if((Read-ModJson $file).enabled.Count -ne 0){throw 'Disable did not persist'}
if(@(Get-ChildItem -LiteralPath $args[1] -Filter '*.tmp').Count){throw 'Settings staging files leaked'}
''',tmp_path)
