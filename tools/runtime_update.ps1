# Runtime release updates. No archive code, native binary or verifier script is
# executed during download/validation. Reuses CHMOD's strict JSON/path primitives.
Add-Type -AssemblyName System.Net.Http
. (Join-Path $PSScriptRoot 'pe_imports.ps1')
$script:Ch2k8UpdateRepository='kima1810/CH2K8-recomp'
$script:Ch2k8UpdateRepositoryId=1411943368
function Get-Ch2k8UpdateState([string]$Root){return Get-ModPath $Root 'port/userdata/runtime-updates'}
function Write-Ch2k8UpdateStatus([string]$Job,[string]$Phase,[string]$Message,[bool]$Done=$false,[bool]$Success=$false){
    Write-ModJson (Get-ModPath $Job 'status.json') ([ordered]@{phase=$Phase;message=$Message;done=$Done;success=$Success})
}
function Receive-Ch2k8UpdateFile([string]$Url,[string]$Output,[long]$Limit,[int]$Seconds=300){
    $uri=[uri]$Url
    $handler=New-Object Net.Http.HttpClientHandler;$handler.AllowAutoRedirect=$false
    $client=New-Object Net.Http.HttpClient($handler);$client.Timeout=[TimeSpan]::FromSeconds($Seconds)
    $client.DefaultRequestHeaders.UserAgent.ParseAdd('CH2K8-Recomp-Updater/1')
    $client.DefaultRequestHeaders.Accept.ParseAdd('application/vnd.github+json')
    $cancel=New-Object Threading.CancellationTokenSource;$cancel.CancelAfter($Seconds*1000)
    try{
        for($redirect=0;$redirect -le 5;$redirect++){
            if($uri.Scheme -cne 'https' -or $uri.UserInfo -or $uri.Port -ne 443 -or $uri.Host -cnotin @('api.github.com','github.com','release-assets.githubusercontent.com','objects.githubusercontent.com')){throw 'Update redirected outside approved HTTPS GitHub hosts.'}
            $response=$client.GetAsync($uri,[Net.Http.HttpCompletionOption]::ResponseHeadersRead,$cancel.Token).GetAwaiter().GetResult()
            try{
                if([int]$response.StatusCode -in @(301,302,303,307,308)){
                    if(-not $response.Headers.Location){throw 'Invalid GitHub redirect.'}
                    $uri=New-Object Uri($uri,$response.Headers.Location);continue
                }
                if([int]$response.StatusCode -eq 403 -or [int]$response.StatusCode -eq 429){throw 'GitHub request was denied or rate limited. Try again later.'}
                if(-not $response.IsSuccessStatusCode){throw ('GitHub request failed (HTTP '+[int]$response.StatusCode+').')}
                if($response.Content.Headers.ContentLength -and $response.Content.Headers.ContentLength -gt $Limit){throw 'Update download exceeds size limit.'}
                $stream=$response.Content.ReadAsStreamAsync().GetAwaiter().GetResult()
                $file=[IO.File]::Open($Output,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
                try{
                    $buffer=New-Object byte[] (128KB);$total=0L
                    while(($read=$stream.ReadAsync($buffer,0,$buffer.Length,$cancel.Token).GetAwaiter().GetResult()) -gt 0){
                        $total+=$read;if($total -gt $Limit){throw 'Update download exceeds size limit.'};$file.Write($buffer,0,$read)
                    }
                    $file.Flush($true)
                }finally{$file.Dispose();$stream.Dispose()}
                return
            }finally{$response.Dispose()}
        }
        throw 'Too many GitHub redirects.'
    }finally{$cancel.Dispose();$client.Dispose();$handler.Dispose()}
}
function Select-Ch2k8Release($Releases){
    $published=@($Releases|Where-Object{$_.draft -eq $false -and $_.published_at}|Sort-Object @{Expression={[DateTimeOffset]::Parse($_.published_at)};Descending=$true},@{Expression={[long]$_.id};Descending=$true})
    if(-not $published.Count){throw 'GitHub has no published releases.'}
    $release=$published[0]
    $assets=@($release.assets|Where-Object{$_.state -ceq 'uploaded' -and $_.name -cmatch '^CH2K8-[A-Za-z0-9_.-]+-Windows-x64(?:-[A-Za-z0-9_.-]+)?\.zip$'}|Sort-Object @{Expression={[DateTimeOffset]::Parse($_.updated_at)};Descending=$true},@{Expression={[long]$_.id};Descending=$true})
    if(-not $assets.Count){throw 'The latest release has no prebuilt CH2K8 Windows x64 ZIP. Source archives cannot update the runtime.'}
    $asset=$assets[0]
    if($asset.size -le 0 -or $asset.size -gt 512MB -or $asset.digest -cnotmatch '^sha256:[0-9a-f]{64}$'){throw 'The Windows release needs a GitHub SHA256 digest and must be at most 512 MiB.'}
    $prefix='https://github.com/'+$script:Ch2k8UpdateRepository+'/releases/download/'
    if(-not ([string]$asset.browser_download_url).StartsWith($prefix,[StringComparison]::Ordinal)){throw 'Unexpected release asset URL.'}
    return [pscustomobject]@{release=$release;asset=$asset;sha256=$asset.digest.Substring(7)}
}
function Get-Ch2k8LatestRelease([string]$Job){
    $repo=Get-ModPath $Job 'repository.json';$releases=Get-ModPath $Job 'releases.json'
    Receive-Ch2k8UpdateFile ('https://api.github.com/repos/'+$script:Ch2k8UpdateRepository) $repo 1MB 30
    $identity=Read-ModJson $repo
    if([long]$identity.id -ne $script:Ch2k8UpdateRepositoryId -or $identity.full_name -cne $script:Ch2k8UpdateRepository){throw 'GitHub repository identity differs from the official recomp.'}
    Receive-Ch2k8UpdateFile ('https://api.github.com/repos/'+$script:Ch2k8UpdateRepository+'/releases?per_page=100') $releases 4MB 30
    return Select-Ch2k8Release (Read-ModJson $releases 4MB)
}
function Assert-Ch2k8UpdatePayloadPath([string]$Path){
    $top=$Path.Split('/')[0]
    if($Path.Contains('/')){
        if($top -cnotin @('tools','docs','sdk','licenses','examples')){throw "Release contains protected or unsupported content: $Path"}
        if($top -ceq 'tools' -and $Path -cnotmatch '^tools/[A-Za-z0-9_.-]+\.ps1$'){throw 'Release tools must be launcher PowerShell files.'}
    }elseif($Path -cnotin @('ch2k8.exe','rexruntime.dll','rexgpu-xenos.dll','ch2k8_tools.exe','ch2k8_asset_codec.dll','ch2k8_assets_check.exe','ch2k8_vfs_check.exe','gamecontrollerdb.txt','CONTROLLER_LICENSE.txt','NATIVE_ASSET_LICENSES.txt','XENIA_TEXTURE_LICENSE.txt','beta-version.json','chmod-runtime.json','runtime-update.json','SHA256SUMS.txt','Launch CH2K8.cmd','BETA_TESTING.md','START HERE.md') -and $Path -cnotmatch '^(msvcp|vcruntime|concrt|vccorlib)[A-Za-z0-9_]+\.dll$'){throw "Unsupported release root file: $Path"}
}
function Expand-Ch2k8RuntimeRelease([string]$Archive,[string]$Destination){
    $null=[IO.Directory]::CreateDirectory($Destination)
    $zip=[IO.Compression.ZipFile]::OpenRead($Archive)
    try{
        if($zip.Entries.Count -gt 12000){throw 'Release has too many archive entries.'}
        $inventories=@($zip.Entries|Where-Object{$_.FullName -ceq 'SHA256SUMS.txt' -or $_.FullName.EndsWith('/SHA256SUMS.txt',[StringComparison]::Ordinal)})
        if($inventories.Count -ne 1){throw 'Release ZIP needs exactly one SHA256SUMS.txt inventory.'}
        $prefix=$inventories[0].FullName.Substring(0,$inventories[0].FullName.Length-'SHA256SUMS.txt'.Length)
        if($prefix -and $prefix -cnotmatch '^[A-Za-z0-9_.-]+/$'){throw 'Release ZIP wrapper must be one portable directory.'}
        $seen=@{};$total=0L
        foreach($entry in $zip.Entries){
            $name=$entry.FullName
            if($name.Contains('\') -or -not $name.StartsWith($prefix,[StringComparison]::Ordinal)){throw 'Release archive path escapes its wrapper.'}
            $mode=([long]$entry.ExternalAttributes -shr 16) -band 0xF000
            if($mode -notin @(0,0x8000,0x4000) -or ($entry.ExternalAttributes -band 0x400)){throw 'Release symlink/reparse entry rejected.'}
            $relative=$name.Substring($prefix.Length).TrimEnd('/')
            if(-not $relative){continue}
            $target=Get-ModPath $Destination $relative -SavePath
            if($seen.ContainsKey($relative)){throw 'Duplicate/case-colliding release archive path.'};$seen[$relative]=$true
            if($name.EndsWith('/')){if($relative.Split('/')[0] -cnotin @('tools','docs','sdk','licenses','examples')){throw 'Unsupported release directory.'};$null=[IO.Directory]::CreateDirectory($target);continue}
            Assert-Ch2k8UpdatePayloadPath $relative
            $total+=$entry.Length
            if($entry.Length -gt 256MB -or $total -gt 2GB -or ($entry.Length -gt 1MB -and $entry.Length -gt 200*[Math]::Max(1,$entry.CompressedLength))){throw 'Release decompression limits exceeded.'}
            $null=[IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($target))
            $input=$entry.Open();$output=[IO.File]::Open($target,[IO.FileMode]::CreateNew)
            try{
                $buffer=New-Object byte[] (128KB);$written=0L
                while(($count=$input.Read($buffer,0,$buffer.Length)) -gt 0){$written+=$count;if($written -gt $entry.Length -or $written -gt 256MB){throw 'Release entry expands beyond declared bounds.'};$output.Write($buffer,0,$count)}
                if($written -ne $entry.Length){throw 'Truncated release archive entry.'}
            }finally{$output.Dispose();$input.Dispose()}
        }
    }finally{$zip.Dispose()}
}
function Assert-Ch2k8RuntimeRelease([string]$Folder,[string]$CurrentRuntime){
    $inventory=Get-ModPath $Folder 'SHA256SUMS.txt'
    if((Get-Item -LiteralPath $inventory).Length -gt 2MB){throw 'Release checksum inventory exceeds limit.'}
    $hashes=@{}
    foreach($line in [IO.File]::ReadAllLines($inventory)){
        if($line -cnotmatch '^([0-9a-f]{64})  (.+)$'){throw 'Malformed release checksum inventory.'}
        $digest=$matches[1];$relative=$matches[2]
        if($relative -ceq 'SHA256SUMS.txt' -or $hashes.ContainsKey($relative)){throw 'Duplicate/self-referencing release checksum.'}
        Assert-Ch2k8UpdatePayloadPath $relative
        $file=Get-ModPath $Folder $relative -SavePath
        if((Get-ModHash $file) -cne $digest){throw "Release checksum mismatch: $relative"};$hashes[$relative]=$digest
    }
    foreach($item in Get-ModTree $Folder 12000){if(-not $item.PSIsContainer){$r=$item.FullName.Substring($Folder.TrimEnd('\').Length+1).Replace('\','/');if($r -cne 'SHA256SUMS.txt' -and -not $hashes.ContainsKey($r)){throw "Unlisted release payload: $r"}}}
    if(-not $hashes.ContainsKey('runtime-update.json')){throw 'The latest published ZIP predates automatic runtime updates. Download retained; installed SDK/runtime preserved. The publisher must release an updater-compatible build.'}
    foreach($required in @('ch2k8.exe','rexruntime.dll','rexgpu-xenos.dll','ch2k8_tools.exe','tools/launch_ch2k8.ps1','tools/chmod.ps1','tools/chmod_ui.ps1','tools/runtime_update.ps1','tools/update_runtime.ps1','tools/pe_imports.ps1','tools/beta_diagnostics.ps1','docs/formats/chmod.schema.json','docs/formats/hook_registry.json','gamecontrollerdb.txt','runtime-update.json','chmod-runtime.json','beta-version.json','msvcp140.dll','vcruntime140.dll','vcruntime140_1.dll','msvcp140_atomic_wait.dll')){if(-not $hashes.ContainsKey($required)){throw "Release is incomplete: missing $required. Ask the publisher for an updater-compatible runtime ZIP."}}
    $meta=Read-ModJson (Get-ModPath $Folder 'runtime-update.json')
    Assert-ModFields $meta @('format','bootstrap_protocol','platform','package_type','xex_sha256','mod_api')
    foreach($n in @($meta.format,$meta.bootstrap_protocol)){if($n -isnot [int] -and $n -isnot [long]){throw 'Update protocol versions must be integers.'}}
    Assert-ModText $meta.mod_api '^\d+\.\d+\.\d+$'
    if($meta.format -ne 1 -or $meta.bootstrap_protocol -ne 1 -or $meta.platform -cne 'windows-x64' -or $meta.package_type -cne 'runtime' -or $meta.xex_sha256 -cne $script:ChmodXex){throw 'Release update protocol/game/platform is incompatible.'}
    $receipt=Read-ModJson (Get-ModPath $Folder 'chmod-runtime.json')
    Assert-ModFields $receipt @('mod_api','xex_sha256','exe_sha256','hooks','extension_abis','capabilities') @('source_revision','sdk_revision','build_note','runtime_files')
    Assert-ModText $receipt.mod_api '^\d+\.\d+\.\d+$'
    foreach($array in @('hooks','extension_abis','capabilities')){if($receipt.$array -isnot [array]){throw 'Runtime capability receipt arrays are malformed.'}}
    if($receipt.xex_sha256 -cne $script:ChmodXex -or $receipt.exe_sha256 -cne $hashes['ch2k8.exe'] -or $receipt.mod_api -cne $meta.mod_api){throw 'Release runtime capability receipt differs.'}
    if('runtime_files' -cin $receipt.PSObject.Properties.Name){
        Assert-ModFields $receipt.runtime_files @('rexruntime.dll','rexgpu-xenos.dll')
        foreach($name in @('rexruntime.dll','rexgpu-xenos.dll')){if($receipt.runtime_files.$name -cne $hashes[$name]){throw "Runtime capability receipt DLL differs: $name"}}
    }
    $version=Read-ModJson (Get-ModPath $Folder 'beta-version.json')
    if($version.platform -cne 'windows-x64' -or $version.game_data_included -isnot [bool] -or $version.game_data_included -ne $false){throw 'Release metadata is not a game-data-free Windows runtime.'}
    foreach($binary in @('ch2k8.exe','rexruntime.dll','rexgpu-xenos.dll','ch2k8_tools.exe')){
        if($version.build_files.$binary -cne $hashes[$binary]){throw "Release build identity differs: $binary"}
        # Static PE parsing only; no LoadLibrary or dependency/verifier execution.
        $file=Get-ModPath $Folder $binary;$b=[IO.File]::ReadAllBytes($file)
        if($b.Length -lt 256 -or $b[0] -ne 77 -or $b[1] -ne 90){throw 'Release binary is not PE.'}
        $pe=[BitConverter]::ToUInt32($b,60)
        if($pe -gt $b.Length-26 -or [BitConverter]::ToUInt32($b,$pe) -ne 0x4550 -or [BitConverter]::ToUInt16($b,$pe+4) -ne 0x8664 -or [BitConverter]::ToUInt16($b,$pe+24) -ne 0x20b){throw 'Release binaries must be PE32+ Windows x64.'}
    }
    $system='advapi32 bcrypt cfgmgr32 combase comdlg32 crypt32 cryptbase dbgcore dbghelp d3d12 d3dcompiler_47 dxgi dwmapi gdi32 imm32 iphlpapi kernel32 kernelbase mswsock ncrypt normaliz ntdll ole32 oleaut32 powrprof psapi propsys rpcrt4 sechost secur32 setupapi shell32 shlwapi shcore user32 userenv uxtheme version winhttp wininet winmm wintrust ws2_32 wtsapi32 ucrtbase' -split ' '
    foreach($binary in Get-ChildItem -LiteralPath $Folder -File|Where-Object{$_.Extension -in @('.exe','.dll')}){
        foreach($import in Get-PeImports $binary.FullName){
            if($hashes.ContainsKey($import) -or $import -match '^(api-ms-win-|ext-ms-win-)' -or ($import -replace '\.dll$','') -in $system){continue}
            throw "Release has an unbundled dependency: $($binary.Name) -> $import. Current runtime preserved."
        }
    }
    if($CurrentRuntime -and [IO.File]::Exists((Join-Path $CurrentRuntime 'chmod-runtime.json'))){
        $old=Read-ModJson (Join-Path $CurrentRuntime 'chmod-runtime.json')
        if([version]$receipt.mod_api -lt [version]$old.mod_api){throw 'The latest published release predates your installed mod API. Download retained, current runtime preserved; wait for a compatible GitHub release.'}
        foreach($c in $old.capabilities){if($c -cnotin $receipt.capabilities){throw "Release removes installed capability $c. Current runtime preserved."}}
        foreach($abi in $old.extension_abis){if($abi -notin $receipt.extension_abis){throw "Release does not preserve native ABI $abi. Current runtime preserved."}}
    }
    return $receipt
}
function Get-Ch2k8PointerRuntime([string]$Root,$Pointer){
    Assert-ModFields $Pointer @('format','release')
    if(($Pointer.format -isnot [int] -and $Pointer.format -isnot [long]) -or $Pointer.format -ne 1){throw 'Unknown runtime pointer format.'}
    if($null -eq $Pointer.release){return $Root}
    Assert-ModText $Pointer.release '^[0-9a-f]{64}$'
    return Get-ModPath (Get-Ch2k8UpdateState $Root) ('releases/'+$Pointer.release)
}
function Get-Ch2k8ActiveRuntime([string]$Root){
    $current=Get-ModPath (Get-Ch2k8UpdateState $Root) 'current.json'
    if(-not [IO.File]::Exists($current)){return $Root}
    $folder=Get-Ch2k8PointerRuntime $Root (Read-ModJson $current)
    if($folder -ine $Root){$null=Assert-Ch2k8RuntimeRelease $folder ''}
    return $folder
}
function Set-Ch2k8RuntimePointer([string]$Root,$Next){
    $state=Get-Ch2k8UpdateState $Root;$current=Get-ModPath $state 'current.json'
    $previous=if([IO.File]::Exists($current)){Read-ModJson $current}else{[pscustomobject]@{format=1;release=$null}}
    $null=Get-Ch2k8PointerRuntime $Root $Next
    # Previous first, current atomically last. Crash before current commit leaves
    # the old runtime active; no binaries/settings need partial-write recovery.
    Write-ModJson (Get-ModPath $state 'previous.json') $previous
    Write-ModJson $current $Next
}
function Install-Ch2k8LatestRuntime([string]$Root,[string]$CurrentRuntime,[string]$Job,[switch]$Rollback){
    $state=Get-Ch2k8UpdateState $Root;$null=[IO.Directory]::CreateDirectory($state)
    try{$lock=[IO.File]::Open((Get-ModPath $state 'update.lock'),[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)}catch{throw 'Another runtime update is in progress.'}
    $launchLock=$null
    try{
        # Shares the launcher's exclusion; never close a running game or dialog.
        $launchLock=[IO.File]::Open((Get-ModPath $Root 'port/userdata/mod-launch.lock'),[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
        if(Get-Process ch2k8 -ErrorAction SilentlyContinue){throw 'Close the game yourself before updating or rolling back.'}
        if($Rollback){
            $prior=Get-ModPath $state 'previous.json'
            if(-not [IO.File]::Exists($prior)){throw 'No previous runtime update is available.'}
            $pointer=Read-ModJson $prior;$folder=Get-Ch2k8PointerRuntime $Root $pointer
            if($folder -ine $Root){$null=Assert-Ch2k8RuntimeRelease $folder ''}
            Set-Ch2k8RuntimePointer $Root $pointer
            return 'Previous runtime restored. Restart the launcher to use it.'
        }
        Write-Ch2k8UpdateStatus $Job 'Checking' 'Checking the latest published GitHub Windows release (including beta releases).'
        $candidate=Get-Ch2k8LatestRelease $Job
        $selected=Get-ModPath $state 'current.json'
        if([IO.File]::Exists($selected) -and (Read-ModJson $selected).release -ceq $candidate.sha256){
            $folder=Get-Ch2k8PointerRuntime $Root (Read-ModJson $selected)
            $null=Assert-Ch2k8RuntimeRelease $folder $CurrentRuntime
            return 'The latest compatible GitHub runtime is already installed.'
        }
        Write-Ch2k8UpdateStatus $Job 'Downloading' ('Downloading '+$candidate.asset.name)
        $archive=Get-ModPath $Job 'release.zip'
        Receive-Ch2k8UpdateFile $candidate.asset.browser_download_url $archive 512MB
        if((Get-Item -LiteralPath $archive).Length -ne [long]$candidate.asset.size -or (Get-ModHash $archive) -cne $candidate.sha256){throw 'GitHub release archive size/SHA256 differs. Nothing installed.'}
        Write-Ch2k8UpdateStatus $Job 'Verifying' 'Verifying every payload hash, update protocol and mod compatibility without executing downloaded code.'
        $stage=Get-ModPath $Job 'payload';Expand-Ch2k8RuntimeRelease $archive $stage
        $null=Assert-Ch2k8RuntimeRelease $stage $CurrentRuntime
        $destination=Get-ModPath $state ('releases/'+$candidate.sha256)
        $null=[IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($destination))
        if([IO.Directory]::Exists($destination)){$null=Assert-Ch2k8RuntimeRelease $destination $CurrentRuntime}else{[IO.Directory]::Move($stage,$destination)}
        $current=Get-ModPath $state 'current.json'
        if([IO.File]::Exists($current) -and (Read-ModJson $current).release -ceq $candidate.sha256){return 'The latest compatible GitHub runtime is already installed.'}
        if(Get-Process ch2k8 -ErrorAction SilentlyContinue){throw 'Game started during update. Runtime prepared but activation stopped; close it yourself and retry.'}
        Set-Ch2k8RuntimePointer $Root ([pscustomobject]@{format=1;release=$candidate.sha256})
        return ('Installed '+$candidate.release.tag_name+'. Restart the launcher to use it. Assets, mods and saves were preserved.')
    }finally{if($launchLock){$launchLock.Dispose()};$lock.Dispose()}
}
