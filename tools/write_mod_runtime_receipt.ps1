param([Parameter(Mandatory=$true)][string]$BuildDirectory)
$ErrorActionPreference='Stop'
$exe=Join-Path $BuildDirectory 'ch2k8.exe'
$map=Join-Path $BuildDirectory 'ch2k8.exe.map'
$symbols=Get-Content -LiteralPath $map -Raw
if($symbols -notmatch '__imp__sub_84752968\s+' -or $symbols -notmatch 'sub_84752968\s+[^\r\n]+mod_extensions.cpp.obj'){throw 'Build map lacks the original getter and compiled mod wrapper.'}
if($symbols -notmatch '__imp__sub_848425D8\s+' -or $symbols -notmatch 'sub_848425D8\s+[^\r\n]+mod_extensions.cpp.obj' -or $symbols -notmatch 'mod_framework.cpp.obj'){throw 'Build map lacks ABI 2 framework/setter adapter.'}
$repo=Split-Path -Parent $PSScriptRoot
$inventory=Get-Content -LiteralPath (Join-Path $repo 'sdk/hooks.json') -Raw|ConvertFrom-Json
foreach($hook in $inventory.package_hooks){if($hook.guest_address){
    $symbol='sub_'+$hook.guest_address
    if($symbols -notmatch ('__imp__'+$symbol+'\s+') -or $symbols -notmatch ($symbol+'\s+[^\r\n]+mod_(extensions|presentation).cpp.obj')){throw "Missing compiled adapter/original for $($hook.id)"}
}}
$revision=(& git -C $repo rev-parse HEAD | Out-String).Trim()
if($LASTEXITCODE -ne 0){throw 'Cannot identify source revision'}
$receipt=[ordered]@{mod_api='1.2.0';xex_sha256='71e8983d1cc009e485696aad19b5fa4b4661761870e2c8972717b932c1e4be36';exe_sha256=(Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.ToLowerInvariant();hooks=@('player.weight.read');source_revision=$revision;sdk_revision='bd833a2ab69d305f99ddf57418fc38ffec8af93d';build_note='Compiled from working tree with local project/SDK patches. Link-map evidence only; gameplay acceptance pending.'}
$receipt.mod_api=$inventory.mod_api
$receipt.hooks=@($inventory.package_hooks|ForEach-Object{$_.id})
$receipt.extension_abis=@($inventory.extension_abis)
$receipt.capabilities=@($inventory.capabilities)+@('runtime.sparse_assets')
$receipt.runtime_files=[ordered]@{}
foreach($name in @('rexruntime.dll','rexgpu-xenos.dll')){$receipt.runtime_files[$name]=(Get-FileHash -LiteralPath (Join-Path $BuildDirectory $name) -Algorithm SHA256).Hash.ToLowerInvariant()}
$target=Join-Path $BuildDirectory 'chmod-runtime.json'
$temp=$target+'.tmp'
$receipt|ConvertTo-Json -Depth 5|Set-Content -LiteralPath $temp -Encoding UTF8
Move-Item -LiteralPath $temp -Destination $target -Force
