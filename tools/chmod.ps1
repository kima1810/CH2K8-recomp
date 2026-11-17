# CHMOD API 1.x: source-bound data overlays and isolated native roster exposure.
Add-Type -AssemblyName System.IO.Compression.FileSystem
$script:ChmodXex = '71e8983d1cc009e485696aad19b5fa4b4661761870e2c8972717b932c1e4be36'
function Assert-ModFields($Object, [string[]]$Required, [string[]]$Optional = @()) {
    if ($null -eq $Object -or $Object -isnot [pscustomobject]) { throw 'Expected a JSON object.' }
    foreach ($key in $Required) { if ($key -cnotin $Object.PSObject.Properties.Name) { throw "Missing mod field: $key" } }
    foreach ($key in $Object.PSObject.Properties.Name) { if ($key -cnotin ($Required + $Optional)) { throw "Unsupported mod field: $key" } }
}
function Assert-ModText($Value, [string]$Pattern) {
    if ($Value -isnot [string] -or $Value.Length -gt 512 -or $Value -cnotmatch $Pattern) { throw "Invalid mod value: $Value" }
}
function Get-ChmodSdkInventory {
    $path=Join-Path (Split-Path -Parent $PSScriptRoot) 'docs/formats/hook_registry.json'
    return Read-ModJson $path
}
function Get-ModPath([string]$Root, [string]$Relative, [switch]$SavePath) {
    # Portable Windows subset: disallow ADS, aliases, UNC, devices and traversal.
    $pattern=if($SavePath){'^[A-Za-z0-9_ ./-]+$'}else{'^[A-Za-z0-9_./-]+$'}
    if ($Relative.Length -gt 220 -or $Relative -cnotmatch $pattern) { throw "Unsafe mod path: $Relative" }
    foreach ($part in $Relative.Split('/')) {
        if (-not $part -or $part -in @('.', '..') -or $part.EndsWith('.') -or $part.EndsWith(' ') -or $part -match '^(CON|PRN|AUX|NUL|COM[0-9]|LPT[0-9])(\.|$)') { throw "Unsafe mod path: $Relative" }
    }
    $base = [IO.Path]::GetFullPath($Root).TrimEnd('\')
    $target = [IO.Path]::GetFullPath((Join-Path $base $Relative))
    if (-not $target.StartsWith($base + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Mod path escapes root.' }
    $cursor = $target
    while ($cursor) {
        if ([IO.File]::Exists($cursor) -or [IO.Directory]::Exists($cursor)) {
            if (([IO.File]::GetAttributes($cursor) -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw "Mod symlink/junction rejected: $cursor" }
        }
        $cursor = [IO.Path]::GetDirectoryName($cursor)
    }
    return $target
}
function Read-ModJson([string]$Path, [long]$Limit=1MB) {
    if ((Get-Item -LiteralPath $Path).Length -gt $Limit) { throw 'Metadata exceeds size limit.' }
    $text=[IO.File]::ReadAllText($Path)
    # ConvertFrom-Json accepts repeated identical keys (last wins). Reject them
    # before deserialization, including Unicode-escaped aliases and deep input.
    $tokens=[regex]::Matches($text,'"(?:[^"\\\x00-\x1f]|\\(?:["\\/bfnrt]|u[0-9a-fA-F]{4}))*"|[{}\[\],:]|true|false|null|-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?')
    $stack=New-Object 'Collections.Generic.List[object]'; $end=0; $previous=''
    foreach($token in $tokens) {
        if($text.Substring($end,$token.Index-$end) -notmatch '^\s*$'){throw 'Invalid JSON token.'}
        $end=$token.Index+$token.Length; $v=$token.Value
        if($v -eq '{' -or $v -eq '[') {
            if($stack.Count -ge 32){throw 'JSON nesting limit exceeded.'}
            $stack.Add(@{object=($v -eq '{');key=($v -eq '{');seen=@{}})
        } elseif($v -eq '}' -or $v -eq ']') {
            if($previous -eq ','){throw 'Trailing JSON comma is invalid.'}
            if(-not $stack.Count){throw 'Invalid JSON nesting.'};$stack.RemoveAt($stack.Count-1)
        } elseif($stack.Count) {
            $frame=$stack[$stack.Count-1]
            if($v -eq ',' -and $frame.object){$frame.key=$true}
            elseif($v -eq ':'){$frame.key=$false}
            elseif($v.StartsWith('"') -and $frame.object -and $frame.key){
                $key=$v | ConvertFrom-Json
                if($frame.seen.ContainsKey($key)){throw "Duplicate JSON key: $key"};$frame.seen[$key]=$true
            }
        }
        $previous=$v
    }
    if($stack.Count -or $text.Substring($end) -notmatch '^\s*$'){throw 'Invalid JSON ending.'}
    return $text | ConvertFrom-Json
}
function Get-ModHash([string]$Path) {
    $stream=[IO.File]::OpenRead($Path); $sha=[Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($sha.ComputeHash($stream)).Replace('-','').ToLowerInvariant() }
    finally { $stream.Dispose(); $sha.Dispose() }
}
function Assert-ChmodSettings($Settings) {
    Assert-ModFields $Settings @('version','enabled') @('allow_native_code')
    if($Settings.version -ne 1 -or ($Settings.version -isnot [int] -and $Settings.version -isnot [long]) -or $Settings.enabled -isnot [array]){throw 'Invalid mod settings.'}
    if('allow_native_code' -cin $Settings.PSObject.Properties.Name -and $Settings.allow_native_code -isnot [bool]){throw 'Native-code opt-in must be a boolean.'}
}
function Read-Chmod([string]$Root) {
    $m = Read-ModJson (Get-ModPath $Root 'mod.json')
    Assert-ModFields $m @('schema_version','id','name','author','version','requires','content','capabilities','dependencies','incompatible','assets') @('update_source','roster','uniforms','extensions','description')
    if (($m.schema_version -isnot [int] -and $m.schema_version -isnot [long]) -or $m.schema_version -ne 1) { throw 'Unsupported CHMOD schema.' }
    Assert-ModText $m.id '^[a-z0-9]+(?:[.-][a-z0-9]+)*$'
    Assert-ModText $m.version '^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$'
    foreach ($v in @($m.name,$m.author)) { Assert-ModText $v '^[^\x00-\x1f]{1,120}$' }
    if('description' -cin $m.PSObject.Properties.Name -and ($m.description -isnot [string] -or $m.description.Length -gt 4096)){throw 'Invalid mod description.'}
    Assert-ModFields $m.requires @('xex_sha256','recomp','mod_api')
    Assert-ModText $m.requires.xex_sha256 '^[0-9a-f]{64}$'
    Assert-ModText $m.requires.recomp '^ZMO-beta1$'
    Assert-ModText $m.requires.mod_api '^1\.[0123]\.0$'
    if ($m.requires.recomp -cne 'ZMO-beta1' -or $m.requires.mod_api -cnotin @('1.0.0','1.1.0','1.2.0','1.3.0')) { throw 'Incompatible recomp or mod API.' }
    foreach ($array in @('content','capabilities','dependencies','incompatible','assets')) {
        if ($m.$array -isnot [array]) { throw "Expected mod array: $array" }
    }
    if ($m.assets.Count -gt 4096) { throw 'Invalid asset count.' }
    $expectedContent=@(); $expectedCaps=@()
    if('uniforms' -cin $m.PSObject.Properties.Name){
        if($m.uniforms -isnot [array] -or $m.uniforms.Count -lt 2 -or $m.uniforms.Count -gt 64 -or $m.requires.mod_api -cnotin @('1.2.0','1.3.0')){throw 'Uniform registration requires API 1.2 and paired source-bound banks.'}
        $expectedCaps+='uniform.register'
    }
    if($m.assets.Count -or $m.uniforms.Count){$expectedContent+= 'assets'}
    if('roster' -cin $m.PSObject.Properties.Name){$expectedContent+='rosters';$expectedCaps+='roster.expose'}
    if('extensions' -cin $m.PSObject.Properties.Name){
        if($m.extensions -isnot [array] -or $m.extensions.Count -ne 1 -or $m.requires.mod_api -cnotin @('1.2.0','1.3.0')){throw 'Native extensions require API 1.2/1.3 and one module per package.'}
        $expectedContent+='code'
    }
    if(-not $expectedContent.Count -or @($m.content | Select-Object -Unique).Count -ne $m.content.Count -or
       (@($m.content|Sort-Object) -join ',') -cne (@($expectedContent|Sort-Object) -join ',')){throw 'Content declaration differs from supported package contents.'}
    $seen = @{}
    foreach ($d in $m.dependencies) {
        Assert-ModFields $d @('id','version')
        Assert-ModText $d.id '^[a-z0-9]+(?:[.-][a-z0-9]+)*$'
        Assert-ModText $d.version '^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$'
        if ($d.id -eq $m.id -or $seen.ContainsKey($d.id)) { throw 'Duplicate or self dependency.' }; $seen[$d.id] = $true
    }
    foreach ($id in $m.incompatible) { Assert-ModText $id '^[a-z0-9]+(?:[.-][a-z0-9]+)*$' }
    $seen = @{}; $files = @{'mod.json'=$true}; [long]$total = 0
    foreach ($a in $m.assets) {
        Assert-ModFields $a @('bank_hash','record_index','record_id','record_type','target','source_sha256','file','sha256') @('kind','component','selection','texture_slot')
        foreach ($key in @('bank_hash','record_index','record_id','record_type')) {
            if (($a.$key -isnot [int] -and $a.$key -isnot [long]) -or $a.$key -lt 0 -or $a.$key -gt 4294967295) { throw "Invalid resource integer: $key" }
        }
        $kind=if('kind' -cin $a.PSObject.Properties.Name){$a.kind}else{'dds.replace'}
        Assert-ModText $kind '^(dds\.replace|cloth\.(?:positions|simulation)|court\.scene)$'
        if($kind -cnotin @('dds.replace','cloth.positions','cloth.simulation','court.scene')){throw 'Unsupported asset capability.'}
        if('selection' -cin $a.PSObject.Properties.Name){
            $globalButtonAtlases=@{0=0x001d1bcfL;190=0x4ffa5eb9L;270=0x7542283fL;410=0xacc6d118L;512=0xd948c961L}
            $globalAtlas=$a.bank_hash -eq 3680386632L -and $a.record_index -le 512 -and
                $globalButtonAtlases[[int]$a.record_index] -eq $a.record_id
            $passAtlas=$a.bank_hash -eq 1823768513L -and $a.record_index -eq 142 -and $a.record_id -eq 0x969565e4L
            if($a.selection -cne 'presentation.playstation' -or $kind -cne 'dds.replace' -or $m.requires.mod_api -cne '1.3.0' -or
               (-not $globalAtlas -and -not $passAtlas)) {throw 'Conditional DDS selection requires a known Button Style atlas and API 1.3.'}
        }
        $expectedCaps+=$kind
        $slotBound='texture_slot' -cin $a.PSObject.Properties.Name
        if($slotBound -and ($kind -cne 'dds.replace' -or $a.selection -or
            ($a.texture_slot -isnot [int] -and $a.texture_slot -isnot [long]) -or
            $a.texture_slot -lt 0 -or $a.texture_slot -ge 4096)){
            throw 'Invalid catalog texture slot.'
        }
        if(($kind -ceq 'dds.replace' -and ($a.record_type -ne 0x5c369069 -and
                (-not $slotBound -or $a.record_type -ne 0xe26c9b5dL))) -or
            ($kind -ceq 'cloth.simulation' -and $a.record_type -ne 0xe1124f13L) -or
            ($kind -cin @('cloth.positions','court.scene') -and $a.record_type -ne 0xe26c9b5dL)){
            throw 'Asset kind and Xbox record type differ.'
        }
        foreach ($hash in @($a.source_sha256,$a.sha256)) { Assert-ModText $hash '^[0-9a-f]{64}$' }
        $null = Get-ModPath $Root $a.target
        if($kind -ceq 'dds.replace'){
            if ($slotBound) {
                if ($a.target -cnotmatch '^assets/[^/]+\.(?:iff|cdf)/[^/]+\.(?:txtr|scne)/(?:_support/)?[^/]+\.dds$' -or
                    $a.file -cne $a.target) { throw 'Named DDS payload must mirror its catalog asset path.' }
            } elseif ($a.target -cnotmatch '^assets/[^/]+\.iff/[^/]+\.txtr/texture\.dds$') {
                throw 'DDS target must be an existing TXTR template.'
            }
            if ($a.file -cnotmatch '^assets/.+\.dds$') { throw 'Payload must be an assets DDS file.' }
            if('component' -cin $a.PSObject.Properties.Name){throw 'DDS entries do not take a component index.'}
        }else{
            if($a.component -isnot [int] -and $a.component -isnot [long]){throw 'SCNE component index is required.'}
            if($a.file -cnotmatch '^assets/.+\.dat$'){throw 'SCNE payload must be an assets DAT file.'}
            $namedComponent=if($a.component -eq 1){'scene_gpu'}else{'scene'}
            if($kind -ceq 'court.scene'){
                if($m.requires.mod_api -cne '1.3.0' -or $a.record_id -ne 3192247854L -or
                   $a.component -notin @(0,1) -or $a.target -cnotmatch ('^assets/[^/]+\.iff/[^/]+\.scne/(?:block'+$a.component+'|'+$namedComponent+')\.dat$')){
                    throw 'Court SCNE requires API 1.3, the floor record, and component 0 or 1.'
                }
            }elseif($kind -ceq 'cloth.simulation'){
                if($m.requires.mod_api -cne '1.3.0' -or $a.bank_hash -ne 4198237405L -or $a.component -ne 0 -or
                   $a.target -cnotmatch '^assets/cloth_shorts\.iff/shorts(?:fat|reg|thin)\.e1124f13/resource_data\.dat$'){
                    throw 'Shorts simulation requires a named Xbox rest-position component.'
                }
            }elseif($a.component -ne 0 -or $a.target -cnotmatch '^assets/[^/]+\.iff/[^/]+\.scne/(?:block0|scene)\.dat$'){
                throw 'Only source-compatible embedded cloth component zero is supported.'
            }
        }
        $file = Get-ModPath $Root $a.file
        if ($seen.ContainsKey($a.target)) { throw 'Duplicate target identity.' }; $seen[$a.target] = $true
        $files[$a.file] = $true
        $size = (Get-Item -LiteralPath $file).Length; $total += $size
        if ($size -gt 128MB -or $total -gt 512MB -or (Get-ModHash $file) -cne $a.sha256) { throw 'Mod payload exceeds limits or integrity differs.' }
    }
    foreach($group in @($m.assets | Where-Object kind -CEQ 'court.scene' | Group-Object bank_hash,record_index,record_id)){
        if($group.Count -ne 2 -or (($group.Group.component | Sort-Object) -join ',') -cne '0,1'){
            throw 'Court SCNE requires exactly one CPU and one GPU component in the same package.'
        }
    }
    if('roster' -cin $m.PSObject.Properties.Name){
        Assert-ModFields $m.roster @('file','sha256','header','header_sha256')
        foreach($key in @('sha256','header_sha256')){Assert-ModText $m.roster.$key '^[0-9a-f]{64}$'}
        if($m.roster.file -cnotmatch '^rosters/.+\.ROS$' -or $m.roster.header -cnotmatch '^rosters/.+\.header$'){throw 'Roster payload/header must use the native rosters paths.'}
        foreach($pair in @(@('file','sha256'),@('header','header_sha256'))){
            $p=Get-ModPath $Root $m.roster.($pair[0]); $files[$m.roster.($pair[0])]=$true
            $size=(Get-Item -LiteralPath $p).Length; $total+=$size
            if($size -gt 64MB -or $total -gt 512MB -or (Get-ModHash $p) -cne $m.roster.($pair[1])){throw 'Roster integrity or size differs.'}
        }
    }
    $uniformNames=@{}
    foreach($u in $m.uniforms){
        Assert-ModFields $u @('name','template_hash','template_layout_sha256','folder','files') @('neck_shape')
        if('neck_shape' -cin $u.PSObject.Properties.Name){
            if(($u.neck_shape -isnot [int] -and $u.neck_shape -isnot [long]) -or
               $u.neck_shape -lt 0 -or $u.neck_shape -gt 4 -or $u.name -cnotmatch '^u[xyz]'){
                throw 'A valid neckline belongs to the world alternate bank.'
            }
        }
        Assert-ModText $u.name '^(?:sel)?u[haxyz][0-9]{3,4}\.iff$'
        if(-not $m.roster -and $u.name -cnotmatch '^(?:sel)?u[xyz]'){throw 'Automatic roster linking supports alternate slots only; new Home/Away banks require an explicit native roster.'}
        Assert-ModText $u.folder '^uniforms/(?:sel)?u[haxyz][0-9]{3,4}\.iff$'
        Assert-ModText $u.template_layout_sha256 '^[0-9a-f]{64}$'
        if(($u.template_hash -isnot [int] -and $u.template_hash -isnot [long]) -or $u.template_hash -lt 0 -or $u.template_hash -gt 4294967295){throw 'Invalid uniform template hash.'}
        if($u.folder -cne ('uniforms/'+$u.name) -or $uniformNames.ContainsKey($u.name)){throw 'Uniform folder/name is duplicate or mismatched.'}
        $uniformNames[$u.name]=$true
        if($u.files -isnot [array] -or $u.files.Count -lt 2 -or $u.files.Count -gt 4096){throw 'Invalid uniform file inventory.'}
        $declared=@{}
        foreach($f in $u.files){
            Assert-ModFields $f @('path','sha256');Assert-ModText $f.sha256 '^[0-9a-f]{64}$'
            Assert-ModText $f.path '^[A-Za-z0-9_./-]+$'
            if($declared.ContainsKey($f.path)){throw 'Duplicate uniform component path.'};$declared[$f.path]=$true
            $relative=$u.folder+'/'+$f.path;$p=Get-ModPath $Root $relative;$files[$relative]=$true
            $size=(Get-Item -LiteralPath $p).Length;$total+=$size
            if($size -gt 128MB -or $total -gt 512MB -or (Get-ModHash $p) -cne $f.sha256){throw 'Uniform file integrity/size differs.'}
            if($f.path.EndsWith('.json',[StringComparison]::Ordinal)){$null=Read-ModJson $p}
        }
        if(-not $declared.ContainsKey('asset.json')){throw 'Uniform bank requires its source-bound asset.json.'}
    }
    foreach($e in $m.extensions){
        if($e.abi -eq 1){
            Assert-ModFields $e @('file','sha256','abi','hook')
            Assert-ModText $e.hook '^player\.weight\.read$';$expectedCaps+='hook.player.weight.read'
        }elseif($e.abi -eq 2 -and $m.requires.mod_api -ceq '1.3.0'){
            Assert-ModFields $e @('file','sha256','abi','capabilities','replacements')
            if($e.capabilities -isnot [array] -or -not $e.capabilities.Count -or $e.capabilities.Count -gt 7 -or $e.replacements -isnot [array] -or $e.replacements.Count -gt 2){throw 'ABI 2 requires capability and replacement arrays.'}
            $inventory=Get-ChmodSdkInventory
            $seen=@{};foreach($c in $e.capabilities){
                Assert-ModText $c '^[a-z][a-z0-9_.]+$'
                if($c -cnotin $inventory.capabilities){throw "Unsupported required native capability $c. Update the runtime or disable this mod."}
                if($seen.ContainsKey($c)){throw 'Duplicate extension capability.'};$seen[$c]=$true;$expectedCaps+=$c
            }
            $claims=@{};foreach($r in $e.replacements){Assert-ModText $r '^[a-z][a-z0-9_.]+$';if($r -cnotin @($inventory.package_hooks|Where-Object{'replace' -cin $_.operations}|ForEach-Object{$_.id}) -or $claims.ContainsKey($r) -or -not $seen.ContainsKey('hook.'+$r)){throw 'Replacement claim requires a supported replaceable hook capability and must be unique.'};$claims[$r]=$true}
        }else{throw 'Unsupported extension ABI; ABI 2 needs mod API 1.3.0.'}
        Assert-ModText $e.sha256 '^[0-9a-f]{64}$'
        Assert-ModText $e.file '^code/[A-Za-z0-9_.-]+\.dll$'
        if(($e.abi -isnot [int] -and $e.abi -isnot [long]) -or $e.file -cnotmatch '^code/[A-Za-z0-9_.-]+\.dll$'){throw 'Unsupported native extension ABI/file.'}
        $p=Get-ModPath $Root $e.file;$files[$e.file]=$true;$size=(Get-Item -LiteralPath $p).Length;$total+=$size
        if($size -lt 256 -or $size -gt 64MB -or $total -gt 512MB -or (Get-ModHash $p) -cne $e.sha256){throw 'Native extension integrity or size differs.'}
        Assert-ChmodDll $p
    }
    $expectedCaps=@($expectedCaps | Sort-Object -Unique)
    $choices=@($m.assets|Where-Object{$_.selection})
    $buttonProvider=@($m.extensions|Where-Object{'hook.presentation.button_style' -cin $_.capabilities})
    if($choices.Count -or $buttonProvider.Count){
        $choiceIndices=@($choices.record_index)
        if(270 -notin $choiceIndices -or 410 -notin $choiceIndices -or
           @($choiceIndices|Sort-Object -Unique).Count -ne $choices.Count -or $buttonProvider.Count -ne 1){
            throw 'Button Style requires one SDK provider and one entry per selected controller atlas.'
        }
    }
    if((@($m.capabilities|Sort-Object) -join ',') -cne ($expectedCaps -join ',')){throw 'Capabilities must exactly describe the supported content.'}
    if($m.requires.mod_api -ceq '1.0.0' -and ($expectedCaps -join ',') -cne 'dds.replace'){throw 'New data capabilities require mod API 1.1.0.'}
    if ('update_source' -cin $m.PSObject.Properties.Name) {
        Assert-ModFields $m.update_source @('url')
        Assert-ModText $m.update_source.url '^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/releases(?:/.*)?$'
    }
    foreach ($item in Get-ModTree $Root) { if (-not $item.PSIsContainer -and -not $files.ContainsKey($item.FullName.Substring($Root.TrimEnd('\').Length+1).Replace('\','/'))) { throw "Undeclared package file: $($item.Name)" } }
    return $m
}
function Get-ModTree([string]$Root, [int]$Limit=8192) {
    $null = Get-ModPath $Root 'mod.json'
    $queue = New-Object 'Collections.Generic.Queue[string]'; $queue.Enqueue([IO.Path]::GetFullPath($Root))
    $count = 0
    while ($queue.Count) {
        foreach ($item in Get-ChildItem -LiteralPath $queue.Dequeue() -Force) {
            if (++$count -gt $Limit) { throw 'Too many files/directories.' }
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Mod tree contains a symlink/junction.' }
            $item
            if ($item.PSIsContainer) { $queue.Enqueue($item.FullName) }
        }
    }
}
function Write-ModJson([string]$Path, $Value, [string]$ExpectedHash) {
    $null = [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($Path))
    $temp = $Path + '.' + [guid]::NewGuid().ToString('N') + '.tmp'
    try {
        [IO.File]::WriteAllText($temp, ($Value | ConvertTo-Json -Depth 20))
        if($ExpectedHash -and (-not [IO.File]::Exists($Path) -or (Get-ModHash $Path) -cne $ExpectedHash)){throw 'Mod settings changed in another launcher; the previous selection was retained.'}
        # Windows PowerShell 5.1 binds $null to an empty System.String here.
        # File.Replace interprets that as an invalid backup filename. NullString
        # passes a genuine CLR null while retaining atomic replacement.
        if ([IO.File]::Exists($Path)) { [IO.File]::Replace($temp,$Path,[System.Management.Automation.Language.NullString]::Value) } else { [IO.File]::Move($temp,$Path) }
    } finally { if ([IO.File]::Exists($temp)) { [IO.File]::Delete($temp) } }
}
function Install-Chmod([string]$Source, [string]$ModsRoot, [switch]$ModFolder) {
    if($ModFolder -and -not [IO.Directory]::Exists($Source)){throw 'Choose a folder containing mod.json.'}
    $null = [IO.Directory]::CreateDirectory($ModsRoot)
    $stage = Get-ModPath $ModsRoot ('.install-' + [guid]::NewGuid().ToString('N'))
    $null = [IO.Directory]::CreateDirectory($stage)
    try {
        if ([IO.Directory]::Exists($Source)) {
            $Source = [IO.Path]::GetFullPath($Source).TrimEnd('\')
            if ($stage.StartsWith($Source+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Install destination must be outside the imported folder.' }
            $m = Read-Chmod $Source
            foreach ($item in Get-ModTree $Source) {
                $target = Get-ModPath $stage $item.FullName.Substring($Source.Length+1).Replace('\','/')
                if ($item.PSIsContainer) { $null=[IO.Directory]::CreateDirectory($target) } else { [IO.File]::Copy($item.FullName,$target) }
            }
        } else {
            if ([IO.Path]::GetExtension($Source) -ine '.chmod' -or (Get-Item -LiteralPath $Source).Length -gt 512MB) { throw 'Choose a .chmod package (maximum 512 MiB).' }
            $zip = [IO.Compression.ZipFile]::OpenRead($Source)
            try {
                $seen=@{}; [long]$total=0
                if ($zip.Entries.Count -gt 8192) { throw 'Too many ZIP entries.' }
                foreach ($entry in $zip.Entries) {
                    $relative=$entry.FullName.TrimEnd('/')
                    $target=Get-ModPath $stage $relative
                    if ($seen.ContainsKey($relative)) { throw 'Duplicate ZIP path.' }; $seen[$relative]=$true
                    $unixType=($entry.ExternalAttributes -shr 16) -band 0xF000
                    if ($unixType -ne 0 -and $unixType -ne 0x8000 -and $unixType -ne 0x4000) { throw 'ZIP special file/symlink rejected.' }
                    if ($entry.ExternalAttributes -band 0x400) { throw 'ZIP reparse point rejected.' }
                    $total += $entry.Length
                    if ($entry.Length -gt 128MB -or $total -gt 512MB -or ($entry.Length -gt 1MB -and $entry.Length -gt 200 * [Math]::Max(1,$entry.CompressedLength))) { throw 'ZIP expansion limit exceeded.' }
                    if ($entry.FullName.EndsWith('/')) { $null=[IO.Directory]::CreateDirectory($target); continue }
                    $null=[IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($target))
                    $input=$entry.Open(); $output=[IO.File]::Open($target,[IO.FileMode]::CreateNew)
                    try {
                        $buffer=New-Object byte[] 65536; [long]$written=0
                        while (($n=$input.Read($buffer,0,$buffer.Length)) -gt 0) {
                            $written += $n
                            if ($written -gt $entry.Length -or $written -gt 128MB) { throw 'ZIP actual expansion exceeds limit.' }
                            $output.Write($buffer,0,$n)
                        }
                        if ($written -ne $entry.Length) { throw 'Truncated ZIP entry.' }
                    } finally { $input.Dispose(); $output.Dispose() }
                }
            } finally { $zip.Dispose() }
        }
        $m=Read-Chmod $stage
        # Immutable version directories: a failed update cannot remove the old version.
        if($ModFolder){
            if(@(Get-InstalledChmods $ModsRoot | Where-Object {
                $_.manifest.id -ceq $m.id -and $_.manifest.version -ceq $m.version
            }).Count){throw 'This mod version is already installed.'}
            $destination=Get-ModPath $ModsRoot $m.id
            if(Test-Path -LiteralPath $destination){
                $destination=Get-ModPath $ModsRoot ($m.id+'-'+$m.version)
            }
        }else{
            $destination=Get-ModPath $ModsRoot ($m.id+'/'+$m.version)
        }
        if (Test-Path -LiteralPath $destination) { throw 'This mod version is already installed.' }
        $null=[IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($destination))
        [IO.Directory]::Move($stage,$destination)
        return $m
    } finally {
        # Only remove this function's checked, generated staging path.
        if ([IO.Directory]::Exists($stage)) { $null=Get-ModPath $ModsRoot ([IO.Path]::GetFileName($stage)); [IO.Directory]::Delete($stage,$true) }
    }
}
function Get-InstalledChmods([string]$ModsRoot, [switch]$IncludeInvalid) {
    if (-not [IO.Directory]::Exists($ModsRoot)) { return }
    foreach ($id in Get-ChildItem -LiteralPath $ModsRoot -Directory) {
        if ($id.Name.StartsWith('.')) { continue }
        $candidate = $id.FullName
        try {
            $null = Get-ModPath $ModsRoot ($id.Name+'/mod.json')
            $folders = if (Test-Path -LiteralPath (Join-Path $candidate 'mod.json')) {
                @($id)
            } else {
                @(Get-ChildItem -LiteralPath $candidate -Directory)
            }
        } catch {
            if ($IncludeInvalid) { [pscustomobject]@{root=$candidate;manifest=$null;error=$_.Exception.Message} }
            continue
        }
        foreach ($folder in $folders) {
            try {
                $manifest = Read-Chmod $folder.FullName
                [pscustomobject]@{root=$folder.FullName;manifest=$manifest;error=$null}
            } catch {
                if ($IncludeInvalid) { [pscustomobject]@{root=$folder.FullName;manifest=$null;error=$_.Exception.Message} }
            }
        }
    }
}

function Invoke-ModContract([string]$Command,[string]$Source,[string]$Other,[string[]]$Extra=@()) {
    $root=Split-Path -Parent $PSScriptRoot
    $tool=@((Join-Path $root 'ch2k8_tools.exe'),(Join-Path $root 'port/out/build/win-amd64-vulkan/ch2k8_tools.exe')) | Where-Object {[IO.File]::Exists($_)} | Select-Object -First 1
    if(-not $tool){throw 'Native CHMOD contract tool is missing. Install the complete updated runtime.'}
    $info=New-Object Diagnostics.ProcessStartInfo
    $info.FileName=$tool; $info.UseShellExecute=$false; $info.CreateNoWindow=$true
    $info.RedirectStandardOutput=$true; $info.RedirectStandardError=$true
    $arguments=@($Command,$Source,$Other)+$Extra
    $info.Arguments=($arguments|ForEach-Object{
        if($_.Contains('"')){throw 'Unsupported quote in native contract path.'}; '"'+($_ -replace '(\\+)$','$1$1')+'"'
    }) -join ' '
    $worker=[Diagnostics.Process]::Start($info)
    try{
        $stdout=$worker.StandardOutput.ReadToEndAsync();$stderr=$worker.StandardError.ReadToEndAsync()
        if(-not $worker.WaitForExit(30000)){$worker.Kill();throw 'Native mod contract validation timed out.'}
        $output=$stdout.GetAwaiter().GetResult();$failure=$stderr.GetAwaiter().GetResult()
        if($worker.ExitCode -ne 0){throw "Native mod contract rejected: $failure"}
        # Older tools printed their uniform result and then a second null value.
        if($Command -cin @('vanilla-uniforms','activate-roster-uniforms')){
            $output=$output -creplace '\s+null\s*\z',''
        }
        $result=$output|ConvertFrom-Json
        if($result.ready -ne $true){throw 'Native contract tool did not report ready.'}
        return $result
    }finally{$worker.Dispose()}
}
function Assert-ChmodDll([string]$File) {
    $b=[IO.File]::ReadAllBytes($File)
    if($b.Length -lt 256 -or $b[0] -ne 77 -or $b[1] -ne 90){throw 'Native extension must be a PE DLL.'}
    $pe=[BitConverter]::ToUInt32($b,60)
    if($pe -gt $b.Length-26 -or [BitConverter]::ToUInt32($b,[int]$pe) -ne 17744 -or
       [BitConverter]::ToUInt16($b,[int]$pe+4) -ne 34404 -or
       -not ([BitConverter]::ToUInt16($b,[int]$pe+22) -band 8192) -or
       [BitConverter]::ToUInt16($b,[int]$pe+24) -ne 523){throw 'Native extension must be a Windows x64 DLL.'}
}
function Resolve-Chmods([string]$Game, [string]$ModsRoot, $Selection, [string]$ExpectedXex=$script:ChmodXex,[bool]$AllowCode=$false) {
    if ($Selection -isnot [array]) { throw 'Mod selection must be an array in low-to-high priority order.' }
    $installed=@(Get-InstalledChmods $ModsRoot -IncludeInvalid); $active=@(); $ids=@{}; $replacements=@{}; $conflicts=@(); $roster=$null;$uniforms=@();$extensions=@()
    foreach ($s in $Selection) {
        Assert-ModFields $s @('id','version')
        Assert-ModText $s.id '^[a-z0-9]+(?:[.-][a-z0-9]+)*$'
        Assert-ModText $s.version '^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$'
        $found=@($installed | Where-Object { $_.manifest.id -ceq $s.id -and $_.manifest.version -ceq $s.version })
        if ($found.Count -ne 1 -or $ids.ContainsKey($s.id)) {
            $broken = @($installed | Where-Object {
                $_.error -and ([IO.Path]::GetFileName($_.root) -ceq $s.id -or
                    ($_.root.EndsWith(('\'+$s.id+'\'+$s.version), [StringComparison]::OrdinalIgnoreCase)))
            })
            if ($broken.Count) { throw "Selected mod $($s.id) $($s.version) is invalid: $($broken[0].error)" }
            throw "Missing, ambiguous or duplicate selected mod: $($s.id) $($s.version)"
        }
        $ids[$s.id]=$s.version; $active += $found[0]
    }
    if (-not $active.Count) { return [pscustomobject]@{active=@(); replacements=@(); conflicts=@();roster=$null;uniforms=@();extensions=@()} }
    if ((Get-ModHash (Get-ModPath $Game 'default.xex')) -cne $ExpectedXex) { throw 'Unsupported game/XEX revision.' }
    $catalog=Read-ModJson (Get-ModPath $Game 'assets.json') 32MB
    if ($catalog.platform -cne 'xbox360' -or $catalog.storage -cne 'loose-resources') { throw 'Mods require an Xbox direct loose-resources installation.' }
    $bankIndex=@{};$layoutCache=@{};$textureCatalog=$null;$sceneEdits=@{};$textureEdits=@{}
    $pathAliases=$null
    $aliasFile=Get-ModPath $Game 'asset_path_aliases.json'
    if([IO.File]::Exists($aliasFile)){
        $aliasCatalog=Read-ModJson $aliasFile 8MB
        if($aliasCatalog.version -ne 1){throw 'Unsupported asset path aliases.'}
        $pathAliases=$aliasCatalog.paths
    }
    foreach($entry in $catalog.entries){
        $key=[string]$entry.hash
        if($bankIndex.ContainsKey($key)){throw 'Ambiguous Xbox bank hash in the installation.'}
        $bankIndex[$key]=$entry
    }
    $uniformPixels=@{}
    foreach($mod in $active){
        $registered=@()
        foreach($u in $mod.manifest.uniforms){
            $proof=Invoke-ModContract 'validate-uniform' $Game (Get-ModPath $mod.root $u.folder) @([string]$u.template_hash,$u.name,$u.template_layout_sha256)
            if($bankIndex.ContainsKey([string]$proof.hash)){throw 'Exclusive uniform bank registration collision.'}
            foreach($pixel in $proof.texture_identities){if($uniformPixels.ContainsKey($pixel)){throw 'New uniform textures share an ambiguous owner identity.'};$uniformPixels[$pixel]=$true}
            $bankIndex[[string]$proof.hash]=[pscustomobject]@{hash=$proof.hash;folder=('assets/'+$u.name);added=$true}
            $registered+=[pscustomobject]@{mod=$mod.manifest.id;name=$u.name;hash=$proof.hash;artwork=$proof.artwork;variant=$proof.variant;selection=$proof.selection;neck_shape=$u.neck_shape;source=(Get-ModPath $mod.root $u.folder);files=$u.files;layout=$proof.layout}
        }
        foreach($bank in $registered){
            $pair=@($registered|Where-Object{$_.artwork -eq $bank.artwork -and $_.variant -eq $bank.variant})
            if($pair.Count -ne 2 -or @($pair|Where-Object{$_.selection}).Count -ne 1){throw 'New uniform artwork requires a world/selection pair in the same package.'}
        }
        $uniforms+=$registered
    }
    foreach ($mod in $active) {
        $m=$mod.manifest
        if ($m.requires.xex_sha256 -cne $ExpectedXex) { throw "Wrong game revision: $($m.id)" }
        foreach ($d in $m.dependencies) { if (-not $ids.ContainsKey($d.id) -or $ids[$d.id] -cne $d.version) { throw "Missing dependency $($d.id) $($d.version) for $($m.id)" } }
        foreach ($id in $m.incompatible) { if ($ids.ContainsKey($id)) { throw "Incompatible mods: $($m.id), $id" } }
        foreach($e in $m.extensions){
            if(-not $AllowCode){throw 'This package executes an unsandboxed Windows DLL. Explicit native-code opt-in is required.'}
            $entry=[ordered]@{id=$m.id;version=$m.version;file=($mod.root.Substring([IO.Path]::GetFullPath($ModsRoot).TrimEnd('\').Length+1).Replace('\','/')+'/'+$e.file);sha256=$e.sha256;abi=$e.abi}
            if($e.abi -eq 1){$entry.hook=$e.hook}else{$entry.capabilities=$e.capabilities;$entry.replacements=$e.replacements;$entry.dependencies=@($m.dependencies|ForEach-Object{$_.id})}
            $extensions+=[pscustomobject]$entry
        }
        if($m.roster){
            if($roster){throw 'Multiple active roster packages are exclusive; disable one before switching.'}
            $payload=Get-ModPath $mod.root $m.roster.file; $header=Get-ModPath $mod.root $m.roster.header
            $proof=Invoke-ModContract 'validate-roster' $payload $header
            foreach($route in $proof.uniform_routes){
                foreach($hash in @($route.world_hash,$route.selection_hash)){
                    if(-not $bankIndex.ContainsKey([string]$hash)){throw 'Roster references an unregistered uniform bank. New jersey registration is not enabled.'}
                }
            }
            foreach($u in @($uniforms|Where-Object{$_.mod -ceq $m.id})){
                $routes=@($proof.uniform_routes|Where-Object{$_.world_hash -eq $u.hash -or $_.selection_hash -eq $u.hash})
                if(-not $routes.Count -and $u.variant -ge 2){continue} # Auto-link by native Home/Away artwork identity at launch.
                if(-not $routes.Count){throw 'Registered Home/Away bank is not referenced by this package native roster.'}
                if(-not @($routes|Where-Object{$_.owner -in $proof.team_uniform_owners}).Count){throw 'New uniform roster owner is not assigned to a native team.'}
            }
            $roster=[pscustomobject]@{mod=$m.id;version=$m.version;file=$payload;header=$header;sha256=$m.roster.sha256;header_sha256=$m.roster.header_sha256}
        }
        $courtPairs=@{}
        foreach ($a in $m.assets) {
            $key=[string]$a.bank_hash
            if(-not $bankIndex.ContainsKey($key)){throw 'Missing/ambiguous Xbox bank hash.'}
            $bank=@($bankIndex[$key])
            if($bank[0].added){throw 'Author artwork inside the registered uniform folder; ordinary overrides target existing installation resources only.'}
            if(-not $layoutCache.ContainsKey($key)){
                $layout=Read-ModJson (Get-ModPath $Game ($bank[0].folder+'/asset.json'))
                foreach ($block in $layout.blocks) {
                    foreach ($component in $block.components) {
                        if ((Get-ModHash (Get-ModPath $Game ($bank[0].folder+'/'+$component.path))) -cne $component.sha256) { throw 'Source component changed; use a pristine baseline.' }
                    }
                }
                $layoutCache[$key]=$layout
            }
            $layout=$layoutCache[$key]
            $records=if($layout.paired_resources){$layout.paired_resources}else{$layout.records}
            $record=@($records | Where-Object { $_.index -eq $a.record_index -and $_.id -eq $a.record_id -and $_.type -eq $a.record_type })
            $kind=if($a.kind){$a.kind}else{'dds.replace'}
            if($record.Count -ne 1){throw 'Resource owner/record identity differs.'}
            $requestedTarget=$a.target
            if($pathAliases){
                $pieces=$requestedTarget.Split('/')
                for($n=$pieces.Count;$n -ge 2;$n--){
                    $prefix=($pieces[0..($n-1)] -join '/')
                    $alias=$pathAliases.PSObject.Properties[$prefix]
                    if($alias){
                        $requestedTarget=$alias.Value+$requestedTarget.Substring($prefix.Length)
                        $null=Get-ModPath $Game $requestedTarget
                        break
                    }
                }
            }
            $ownerKey="$key/$($a.record_index)"
            if('texture_slot' -cin $a.PSObject.Properties.Name){
                if($null -eq $textureCatalog){
                    $textureCatalog=Read-ModJson (Get-ModPath $Game 'scene_textures.json') 64MB
                    if($textureCatalog.version -ne 1){throw 'Unsupported named texture catalog.'}
                }
                $owner=@($textureCatalog.scenes|Where-Object {
                    $_.bank -eq $a.bank_hash -and $_.record -eq $a.record_index
                })
                if($owner.Count -ne 1){throw 'Named texture record is missing or ambiguous.'}
                $texture=@($owner[0].textures|Where-Object {$_.slot -eq $a.texture_slot})
                if($texture.Count -ne 1){throw 'Named texture slot is missing or ambiguous.'}
                $target=$texture[0].file
                if($target -cne $requestedTarget -or $texture[0].sha256 -cne $a.source_sha256 -or
                    (Get-ModHash (Get-ModPath $Game $target)) -cne $a.source_sha256){
                    throw 'Named texture path or original digest differs.'
                }
                if($sceneEdits.ContainsKey($ownerKey)){throw 'Named texture overlaps a whole-scene override.'}
                $textureEdits[$ownerKey]=$true
            }elseif($kind -ceq 'dds.replace'){
                $target=$bank[0].folder+'/'+$record[0].folder+'/texture.dds'
                $legacy=if($record[0].legacy_folder){$bank[0].folder+'/'+$record[0].legacy_folder+'/texture.dds'}
                if($requestedTarget -cne $target -and $requestedTarget -cne $legacy){throw 'Resource owner/record identity differs.'}
                $texture=@($layout.textures | Where-Object { $_.path -ceq ($record[0].folder+'/texture.dds') })
                if ($texture.Count -ne 1 -or $texture[0].sha256 -cne $a.source_sha256 -or (Get-ModHash (Get-ModPath $Game $target)) -cne $a.source_sha256) { throw 'DDS source template differs; use a pristine baseline.' }
            }else{
                if($textureEdits.ContainsKey($ownerKey)){throw 'Whole-scene override overlaps a named texture.'}
                $sceneEdits[$ownerKey]=$true
                $r=$record[0]
                $count=if($kind -ceq 'court.scene'){2}else{1}
                if($r.offsets.Count -ne $count -or $layout.blocks.Count -lt $count){throw 'Unexpected SCNE component layout.'}
                $index=[int]$a.component
                $offset=$r.offsets[$index]
                $component=@($layout.blocks[$index].components | Where-Object {$_.start -eq $offset})
                $owners=@($layout.records | Where-Object {$_.offsets.Count -gt $index -and $_.offsets[$index] -eq $offset})
                if($component.Count -ne 1 -or $owners.Count -ne 1 -or $component[0].sha256 -cne $a.source_sha256){
                    throw 'Ambiguous or changed SCNE component owner.'
                }
                $target=$bank[0].folder+'/'+$component[0].path
                $legacy=if($component[0].legacy_path){$bank[0].folder+'/'+$component[0].legacy_path}
                if($requestedTarget -cne $target -and $requestedTarget -cne $legacy){throw 'SCNE component path differs.'}
                $source=Get-ModPath $Game $target
                $payload=Get-ModPath $mod.root $a.file
                if($kind -ceq 'court.scene'){
                    $pairKey="$key/$($a.record_index)"
                    if(-not $courtPairs.ContainsKey($pairKey)){$courtPairs[$pairKey]=@{}}
                    $courtPairs[$pairKey][[string]$index]=@($source,$payload)
                }elseif($kind -ceq 'cloth.simulation'){
                    $null=Invoke-ModContract 'validate-cloth-rest' $source $payload
                }else{
                    $null=Invoke-ModContract 'validate-cloth' $source $payload
                }
            }
            if ($replacements.ContainsKey($target)) {
                if($a.selection -or $replacements[$target].selection){throw 'Conditional Button Style textures conflict with another override; disable the overlapping mod.'}
                if($kind -cne 'dds.replace' -or $replacements[$target].kind -cne 'dds.replace'){throw 'Overlapping component modifications are exclusive.'}
                $conflicts += "$($target): $($replacements[$target].mod) -> $($m.id) (higher priority wins)"
            }
            $replacements[$target]=[pscustomobject]@{target=$target; file=(Get-ModPath $mod.root $a.file); sha256=$a.sha256; mod=$m.id;kind=$kind;selection=$a.selection}
        }
        foreach($pair in $courtPairs.Values){
            $cpu=$pair['0']
            $gpu=$pair['1']
            $null=Invoke-ModContract 'validate-court' $cpu[0] $gpu[0] @($cpu[1],$gpu[1])
        }
    }
    # Exact dependency cycles are rejected, even if all versions are installed.
    $done=@{}; $visiting=@{}
    function Visit-Chmod($id) {
        if ($visiting.ContainsKey($id)) { throw 'Mod dependency cycle.' }; if ($done.ContainsKey($id)) { return }
        $visiting[$id]=$true
        $node=$active | Where-Object { $_.manifest.id -ceq $id }
        foreach ($d in $node.manifest.dependencies) { Visit-Chmod $d.id }
        $visiting.Remove($id); $done[$id]=$true
    }
    foreach ($mod in $active) { Visit-Chmod $mod.manifest.id }
    if($extensions.Count -gt 64){throw 'Native module selection exceeds 64 DLLs.'}
    if(@($extensions|Where-Object{'hook.presentation.button_style' -cin $_.capabilities}).Count -gt 1){throw 'Only one Button Style provider may be enabled.'}
    $legacy=@($extensions|Where-Object{$_.abi -eq 1})
    if($legacy.Count -gt 1 -or ($legacy.Count -and @($extensions|Where-Object{$_.abi -eq 2 -and 'hook.player.weight.read' -cin $_.capabilities}).Count)){throw 'Exclusive player.weight.read hook registration conflict: legacy ABI 1 is exclusive; disable overlapping weight-read mods.'}
    $claims=@{};foreach($e in $extensions){foreach($r in $e.replacements){if($claims.ContainsKey($r)){throw "Exclusive replacement conflict for $r between $($claims[$r]) and $($e.id)."};$claims[$r]=$e.id}}
    # Stable topological module order: dependencies first, then launcher priority.
    $ordered=@();$pending=@($extensions)
    while($pending.Count){
        $next=@($pending|Where-Object{$candidate=$_;$deps=@(($active|Where-Object{$_.manifest.id -ceq $candidate.id}).manifest.dependencies|ForEach-Object{$_.id});-not @($pending|Where-Object{$_.id -cin $deps}).Count}|Select-Object -First 1)
        if(-not $next.Count){throw 'Native module dependency cycle.'}
        $ordered+=$next[0];$pending=@($pending|Where-Object{$_.id -cne $next[0].id})
    }
    return [pscustomobject]@{active=@($active | ForEach-Object { [pscustomobject]@{id=$_.manifest.id;version=$_.manifest.version} }); replacements=@($replacements.Values | Sort-Object target); conflicts=$conflicts;roster=$roster;uniforms=$uniforms;extensions=@($ordered)}
}

function Assert-ChmodLaunchCompatibility($Plan, [string]$Executable, [string]$Renderer) {
    if($plan.extensions.Count){
        $markerPath=Join-Path ([IO.Path]::GetDirectoryName($Executable)) 'chmod-runtime.json'
        if(-not [IO.File]::Exists($markerPath)){throw 'This executable lacks the compiled native mod dispatcher. Install the updated mod runtime first.'}
        $marker=Read-ModJson $markerPath
        Assert-ModFields $marker @('mod_api','xex_sha256','exe_sha256','hooks') @('source_revision','sdk_revision','build_note','extension_abis','capabilities','runtime_files')
        Assert-ModText $marker.mod_api '^1\.[23]\.0$'
        Assert-ModText $marker.xex_sha256 '^[0-9a-f]{64}$';Assert-ModText $marker.exe_sha256 '^[0-9a-f]{64}$'
        if($marker.hooks -isnot [array]){throw 'Native runtime hook registry is malformed.'}
        if($marker.xex_sha256 -cne $script:ChmodXex -or $marker.exe_sha256 -cne (Get-ModHash $Executable) -or 'player.weight.read' -cnotin $marker.hooks){throw 'Native mod runtime capability/revision receipt differs.'}
        foreach($e in $plan.extensions){if($e.abi -eq 2){
            if($marker.mod_api -cne '1.3.0' -or 2 -notin $marker.extension_abis -or $marker.capabilities -isnot [array]){throw 'This module requires the API 1.3 / ABI 2 runtime. Update the recomp.'}
            foreach($cap in $e.capabilities){if($cap -cnotin $marker.capabilities){throw "Runtime lacks required capability $cap for $($e.id). Update the recomp or disable that mod."}}
        }}
        if(@($plan.extensions|Where-Object{'hook.presentation.button_style' -cin $_.capabilities}).Count){
            Assert-ModFields $marker.runtime_files @('rexruntime.dll','rexgpu-xenos.dll')
            foreach($name in @('rexruntime.dll','rexgpu-xenos.dll')){
                Assert-ModText $marker.runtime_files.$name '^[0-9a-f]{64}$'
                if((Get-ModHash (Join-Path ([IO.Path]::GetDirectoryName($Executable)) $name)) -cne $marker.runtime_files.$name){throw "Button Style requires matching $name. Install the complete updated runtime."}
            }
        }
    }
    if (($plan.replacements.Count -or $plan.uniforms.Count) -and $Renderer -eq 'vulkan') { throw 'Asset mods require Direct3D 12.' }
}

function Get-ChmodCacheKey([string]$Game, $Plan, [string]$AssetTool, [bool]$Sparse=$false) {
    if(-not $AssetTool -or -not [IO.File]::Exists((Join-Path $Game 'assets.json'))){return}
    $report=& $AssetTool asset-state $Game
    if($LASTEXITCODE){throw 'Could not check the game assets for changes.'}
    $inputs=($report | ConvertFrom-Json).inputs
    if($inputs -cnotmatch '^[0-9a-f]{64}$'){throw 'Invalid game asset state.'}
    $compatibility=Join-Path $Game '_runtime/compatibility.json'
    $map=Join-Path $Game 'assets.map'
    $stamp=[ordered]@{
        version=2
        sparse=$Sparse
        game=$Game
        inputs=$inputs
        compatibility=$(if([IO.File]::Exists($compatibility)){Get-ModHash $compatibility})
        map=$(if($Sparse -and [IO.File]::Exists($map)){Get-ModHash $map})
        tool=(Get-ModHash $AssetTool)
        plan=$Plan
    }
    $sha=[Security.Cryptography.SHA256]::Create()
    try {
        $bytes=[Text.Encoding]::UTF8.GetBytes(($stamp | ConvertTo-Json -Depth 30 -Compress))
        return [BitConverter]::ToString($sha.ComputeHash($bytes)).Replace('-','').ToLowerInvariant()
    } finally {$sha.Dispose()}
}
function Write-ChmodProgress([string]$Path, [string]$Message, [int]$Done=0, [int]$Total=0) {
    if(-not $Path){return}
    $tmp=$Path+'.stage.tmp'
    try {
        [IO.File]::WriteAllText($tmp,(@{message=$Message;done=$Done;total=$Total}|ConvertTo-Json -Compress))
        if([IO.File]::Exists($Path)){[IO.File]::Replace($tmp,$Path,[System.Management.Automation.Language.NullString]::Value)}
        else{[IO.File]::Move($tmp,$Path)}
    } catch {
        Write-Verbose "Could not publish mod staging progress: $($_.Exception.Message)"
    } finally {
        if([IO.File]::Exists($tmp)){[IO.File]::Delete($tmp)}
    }
}
function New-ChmodCache([string]$Game, [string]$CacheRoot, $Plan, [scriptblock]$Prepare, [string]$AssetTool, [switch]$Sparse, [string]$ProgressFile) {
    if (-not $Plan.replacements.Count -and -not $Plan.uniforms.Count) { return $Game }
    $Game=[IO.Path]::GetFullPath($Game).TrimEnd('\');$CacheRoot=[IO.Path]::GetFullPath($CacheRoot).TrimEnd('\')
    if($CacheRoot -eq $Game -or $CacheRoot.StartsWith($Game+'\',[StringComparison]::OrdinalIgnoreCase) -or $Game.StartsWith($CacheRoot+'\',[StringComparison]::OrdinalIgnoreCase)){throw 'Mod cache must be separate from the game installation.'}
    $null=[IO.Directory]::CreateDirectory($CacheRoot)
    $lockPath=Get-ModPath $CacheRoot 'prepare.lock'
    try{$cacheLock=[IO.File]::Open($lockPath,[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)}catch{throw 'Another launcher is preparing mods. Wait for it to finish.'}
    $stage=Get-ModPath $CacheRoot ('.prepare-'+[guid]::NewGuid().ToString('N'))
    try {
        Write-ChmodProgress $ProgressFile 'Checking the prepared mod cache...'
        $cacheKey=Get-ChmodCacheKey $Game $Plan $AssetTool $Sparse.IsPresent
        if($cacheKey){
            $saved=Get-ModPath $CacheRoot $cacheKey
            if([IO.File]::Exists((Join-Path $saved 'chmod-lock.json')) -and
               [IO.File]::Exists((Join-Path $saved 'assets.map')) -and
               [IO.File]::Exists((Join-Path $saved 'native_dds.index')) -and
               [IO.File]::Exists((Join-Path $saved 'native_audio.index'))){
                Write-ChmodProgress $ProgressFile 'Using the prepared mod cache.' 1 1
                return $saved
            }
            if([IO.Directory]::Exists($saved)){[IO.Directory]::Delete($saved,$true)}
        }
        $null=[IO.Directory]::CreateDirectory($stage)
        if (-not ('ChmodStage' -as [type])) {
            Add-Type -Path (Join-Path $PSScriptRoot 'chmod_stage.cs')
        }
        $bankFolders=@($Plan.replacements | ForEach-Object { ($_.target.Split('/')[0..1] -join '/') } | Sort-Object -Unique)
        $overlay=$false
        if($Sparse -and $AssetTool){
            $request=Join-Path $stage 'overlay-request.json'
            [IO.File]::WriteAllText($request,(ConvertTo-Json -InputObject $bankFolders),[Text.UTF8Encoding]::new($false))
            $init=& $AssetTool initialize-overlay $Game $stage $request
            if($LASTEXITCODE){throw 'Could not initialize the sparse mod cache.'}
            [IO.File]::Delete($request)
            $overlay=($init | ConvertFrom-Json).eligible
        }
        $assetInputs=if($overlay){$bankFolders}else{
            @(Get-ChildItem -LiteralPath (Join-Path $Game 'assets') -Force |
                ForEach-Object {'assets/'+$_.Name})
        }
        $inputs=if($overlay){@('default.xex') + $assetInputs}else{@('_runtime','assets.json','default.xex','asset_edits.json','scene_textures.json') + $assetInputs}
        $null=[IO.Directory]::CreateDirectory((Join-Path $stage 'assets'))
        if(-not [IO.File]::Exists((Join-Path $Game '_runtime/compatibility.json'))){$inputs+='_archive'}
        $copied=0
        $bankCount=@($assetInputs).Count
        Write-ChmodProgress $ProgressFile "Staging asset banks (0/$bankCount)..." 0 $bankCount
        foreach ($name in $inputs) {
            $source=Get-ModPath $Game $name
            if (-not (Test-Path -LiteralPath $source)) { continue }
            $target=Join-Path $stage $name
            if ([IO.Directory]::Exists($source)) {
                [ChmodStage]::CopyTree($source,$target,($name -ceq 'assets' -or $name.StartsWith('assets/')))
            } else {
                [IO.File]::Copy($source,$target)
            }
            if($name.StartsWith('assets/')){
                $copied++
                if($bankCount -le 50 -or $copied % 16 -eq 0 -or $copied -eq $bankCount){
                    Write-ChmodProgress $ProgressFile "Staging asset banks ($copied/$bankCount)..." $copied $bankCount
                }
            }
        }
        $applied=0
        $totalFiles=@($Plan.replacements).Count
        foreach($u in $Plan.uniforms){$totalFiles+=@($u.files).Count}
        Write-ChmodProgress $ProgressFile "Applying mod files (0/$totalFiles)..." 0 $totalFiles
        foreach ($a in $Plan.replacements) {
            if ((Get-ModHash $a.file) -cne $a.sha256) { throw 'Package changed since resolution.' }
            $target=Get-ModPath $stage $a.target
            if([IO.File]::Exists($target)){[IO.File]::Delete($target)}
            [IO.File]::Copy($a.file,$target)
            $applied++
            if($totalFiles -le 50 -or $applied % 16 -eq 0 -or $applied -eq $totalFiles){
                Write-ChmodProgress $ProgressFile "Applying mod files ($applied/$totalFiles)..." $applied $totalFiles
            }
        }
        foreach($u in $Plan.uniforms){
            foreach($f in $u.files){
                $source=Get-ModPath $u.source $f.path
                if((Get-ModHash $source) -cne $f.sha256){throw 'Uniform package changed during preparation.'}
                if($f.path -cne 'asset.json'){
                    $target=Get-ModPath $stage ('assets/'+$u.name+'/'+$f.path)
                    $null=[IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($target));[IO.File]::Copy($source,$target)
                }
                $applied++
                if($totalFiles -le 50 -or $applied % 16 -eq 0 -or $applied -eq $totalFiles){
                    Write-ChmodProgress $ProgressFile "Applying mod files ($applied/$totalFiles)..." $applied $totalFiles
                }
            }
            Write-ModJson (Get-ModPath $stage ('assets/'+$u.name+'/asset.json')) $u.layout
        }
        Write-ChmodProgress $ProgressFile 'Preparing the runtime asset map...'
        if($overlay){
            $prepareArgs=@('prepare-overlay',$stage,$Game)
            if($ProgressFile){$prepareArgs+=@('--progress-file',$ProgressFile)}
            $null=& $AssetTool @prepareArgs
            if($LASTEXITCODE){throw 'Could not prepare the changed mod banks.'}
        }else{& $Prepare $stage}
        $choices=@($Plan.replacements|Where-Object{$_.selection -ceq 'presentation.playstation'}|Sort-Object target)
        if($choices.Count){
            if($choices.Count -lt 2 -or $choices.Count -gt 6){throw 'Conditional Button Style atlases are incomplete.'}
            [IO.File]::WriteAllLines((Join-Path $stage 'native_dds_choices.index'),@('CH2K8_PRESENTATION_DDS_V1')+@($choices|ForEach-Object{$_.target}),[Text.UTF8Encoding]::new($false))
        }
        Write-ModJson (Join-Path $stage 'chmod-lock.json') ([ordered]@{mod_api='1.2.0';baseline=$Game;active=$Plan.active;replacements=$Plan.replacements;conflicts=$Plan.conflicts;roster=$Plan.roster;uniforms=@($Plan.uniforms|ForEach-Object{[ordered]@{name=$_.name;hash=$_.hash;mod=$_.mod;files=$_.files}})})
        if($cacheKey -and (Get-ChmodCacheKey $Game $Plan $AssetTool $Sparse.IsPresent) -cne $cacheKey){
            throw 'Game assets changed while preparing mods. Launch again to use the new files.'
        }
        $destination=Get-ModPath $CacheRoot $(if($cacheKey){$cacheKey}else{[guid]::NewGuid().ToString('N')})
        [IO.Directory]::Move($stage,$destination)
        # Start-Ch2k8 refuses a running game before this function is entered.
        # Remove only our previously published caches, never arbitrary folders.
        foreach($old in Get-ChildItem -LiteralPath $CacheRoot -Directory){
            if($old.FullName -eq $destination -or $old.Name -cnotmatch '^(?:[0-9a-f]{32}|[0-9a-f]{64})$'){continue}
            if($overlay -and -not [IO.File]::Exists((Join-Path $old.FullName 'stock-root.txt'))){continue}
            try{
                $receipt=Get-ModPath $old.FullName 'chmod-lock.json'
                if([IO.File]::Exists($receipt)){
                    $oldPlan=Read-ModJson $receipt 32MB
                    if($oldPlan.mod_api -cin @('1.0.0','1.1.0','1.2.0')){
                        $null=Get-ModPath $CacheRoot $old.Name
                        [IO.Directory]::Delete($old.FullName,$true)
                    }
                }
            }catch{Write-Verbose "Old mod cache retained: $($_.Exception.Message)"}
        }
        return $destination
    } finally {
        if ([IO.Directory]::Exists($stage)) { $null=Get-ModPath $CacheRoot ([IO.Path]::GetFileName($stage)); [IO.Directory]::Delete($stage,$true) }
        $cacheLock.Dispose()
    }
}
function New-ChmodRosterProfile([string]$Baseline,[string]$ProfileRoot,$Plan) {
    if(-not $Plan.roster -and -not $Plan.extensions.Count){return $Baseline}
    $r=$Plan.roster
    if(-not $r){
        $seed=Get-ModPath $Baseline 'B13EBABEBABEBABE/54540818/00000001/Roster.ROS/Roster.ROS'
        $seedHeader=Get-ModPath $Baseline 'B13EBABEBABEBABE/54540818/Headers/00000001/Roster.ROS.header'
        if([IO.File]::Exists($seed) -ne [IO.File]::Exists($seedHeader)){throw 'Baseline roster/header pair is incomplete. Native-code profiles will not guess save contents.'}
        if([IO.File]::Exists($seed)){$r=[pscustomobject]@{mod='baseline-seed';version='1.0.0';file=$seed;header=$seedHeader;sha256=(Get-ModHash $seed);header_sha256=(Get-ModHash $seedHeader)}}
    }
    # Bind persistent data to the entire coherent mod set, not just the roster ID.
    # A changed asset selection or version receives a fresh profile. Existing
    # Legacy saves in either baseline or older profiles are never migrated.
    $descriptor=[ordered]@{api='1.1.0';active=$Plan.active;roster=$(if($r){$r.sha256}else{'builtin-no-seed'});header=$(if($r){$r.header_sha256}else{'none'});assets=@($Plan.replacements|ForEach-Object{[ordered]@{target=$_.target;sha256=$_.sha256}})}
    if($Plan.uniforms.Count){$descriptor.api='1.2.0';$descriptor.uniforms=@($Plan.uniforms|ForEach-Object{[ordered]@{name=$_.name;files=$_.files}})}
    if($Plan.extensions.Count){$descriptor.api='1.2.0';$descriptor.extensions=$Plan.extensions}
    $bytes=[Text.Encoding]::UTF8.GetBytes(($descriptor|ConvertTo-Json -Depth 15 -Compress))
    $sha=[Security.Cryptography.SHA256]::Create()
    try{$key=[BitConverter]::ToString($sha.ComputeHash($bytes)).Replace('-','').ToLowerInvariant()}finally{$sha.Dispose()}
    $null=[IO.Directory]::CreateDirectory($ProfileRoot)
    $destination=Get-ModPath $ProfileRoot $key
    if([IO.Directory]::Exists($destination)){
        $receipt=Read-ModJson (Get-ModPath $destination 'chmod-profile.json')
        if($receipt.key -cne $key){throw 'Isolated roster profile receipt differs. Original saves were not changed.'}
        return $destination
    }
    $stage=Get-ModPath $ProfileRoot ('.profile-'+[guid]::NewGuid().ToString('N'))
    $null=[IO.Directory]::CreateDirectory($stage)
    try{
        if($r){
            foreach($pair in @(@($r.file,$r.sha256),@($r.header,$r.header_sha256))){if((Get-ModHash $pair[0]) -cne $pair[1]){throw 'Roster package changed during activation.'}}
            # Imported packages must be profile-neutral. The local seed is copied verbatim from the same native profile.
            if($Plan.roster){$null=Invoke-ModContract 'validate-roster' $r.file $r.header}
        }
        # Pinned UserProfile::UserProfile default, not an author-controlled XUID.
        $profile='B13EBABEBABEBABE/54540818'
        foreach($name in @('User.USR','Settings.STG')){
            foreach($suffix in @("00000001/$name/$name","Headers/00000001/$name.header")){
                $source=Get-ModPath $Baseline ($profile+'/'+$suffix)
                if([IO.File]::Exists($source)){
                    $target=Get-ModPath $stage ($profile+'/'+$suffix)
                    $null=[IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($target));[IO.File]::Copy($source,$target)
                }
            }
        }
        foreach($suffix in @('00000001/Roster.ROS/Roster.ROS','Headers/00000001/Roster.ROS.header')){
            $source=Get-ModPath $Baseline ($profile+'/'+$suffix)
            if([IO.File]::Exists($source)){
                $backup=Get-ModPath $stage ('baseline-backup/'+$suffix)
                $null=[IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($backup));[IO.File]::Copy($source,$backup)
            }
        }
        if($r){
            $payload=Get-ModPath $stage ($profile+'/00000001/Roster.ROS/Roster.ROS')
            $header=Get-ModPath $stage ($profile+'/Headers/00000001/Roster.ROS.header')
            $null=[IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($payload));$null=[IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($header))
            [IO.File]::Copy($r.file,$payload);[IO.File]::Copy($r.header,$header)
        }
        Write-ModJson (Join-Path $stage 'chmod-profile.json') ([ordered]@{key=$key;roster_mod=$(if($r){$r.mod}else{'builtin'});roster_version=$(if($r){$r.version}else{'none'});selection=$descriptor;policy='isolated-no-legacy-migration'})
        [IO.Directory]::Move($stage,$destination)
        return $destination
    }finally{if([IO.Directory]::Exists($stage)){$null=Get-ModPath $ProfileRoot ([IO.Path]::GetFileName($stage));[IO.Directory]::Delete($stage,$true)}}
}
function Get-ChmodUpdate($Manifest) {
    if(-not $Manifest.update_source){throw 'The author has not declared an update source.'}
    $match=[regex]::Match($Manifest.update_source.url,'^https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/releases(?:/.*)?$')
    if(-not $match.Success){throw 'Unsupported update source.'}
    $repo=$match.Groups[1].Value+'/'+$match.Groups[2].Value
    [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12
    $release=Invoke-RestMethod -Uri ("https://api.github.com/repos/$repo/releases/latest") -Headers @{'User-Agent'='CH2K8-Mods/1.1'} -TimeoutSec 20
    $tag=([string]$release.tag_name) -creplace '^v',''
    Assert-ModText $tag '^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$'
    $assets=@($release.assets|Where-Object {$_.name -clike '*.chmod'})
    if($assets.Count -ne 1){throw 'Latest release must contain exactly one .chmod package; otherwise install a reviewed download manually.'}
    $asset=$assets[0]
    $prefix="https://github.com/$repo/releases/download/"
    if(-not ([string]$asset.browser_download_url).StartsWith($prefix,[StringComparison]::Ordinal) -or $asset.size -le 0 -or $asset.size -gt 512MB){throw 'Update asset source or size is invalid.'}
    return [pscustomobject]@{version=$tag;url=$asset.browser_download_url;bytes=[long]$asset.size;id=$Manifest.id;installed=$Manifest.version}
}
function Compare-ModVersion([string]$Left,[string]$Right) {
    foreach($value in @($Left,$Right)){Assert-ModText $value '^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$'}
    $a=$Left.Split('.');$b=$Right.Split('.')
    for($i=0;$i -lt 3;$i++){
        if($a[$i].Length -ne $b[$i].Length){return [Math]::Sign($a[$i].Length-$b[$i].Length)}
        $comparison=[string]::CompareOrdinal($a[$i],$b[$i]);if($comparison){return [Math]::Sign($comparison)}
    }
    return 0
}
function Install-ChmodUpdate($Update,[string]$ModsRoot,[string]$Game,[string]$Settings,[scriptblock]$Prepare,[string]$CacheRoot,[string]$Executable,[string]$Renderer) {
    if((Compare-ModVersion $Update.version $Update.installed) -le 0){throw 'The author release is not newer than the installed version.'}
    $settingsExist = [IO.File]::Exists($Settings)
    $settingsHash = if ($settingsExist) { Get-ModHash $Settings }
    $old = if ($settingsExist) { Read-ModJson $Settings } else {
        [pscustomobject]@{version=1;enabled=@();allow_native_code=$false}
    }
    Assert-ChmodSettings $old
    $null=[IO.Directory]::CreateDirectory($ModsRoot)
    $download=Get-ModPath $ModsRoot ('.download-'+[guid]::NewGuid().ToString('N')+'.chmod')
    $installed=$null; $committed=$false
    try{
        # WebClient's DownloadFile has no expansion/transfer bound; stream and
        # enforce both the declared release size and the package byte ceiling.
        $request=[Net.HttpWebRequest]::Create($Update.url)
        $request.UserAgent='CH2K8-Mods/1.1';$request.Timeout=20000;$request.ReadWriteTimeout=20000
        $timer=[Diagnostics.Stopwatch]::StartNew();$response=$request.GetResponse()
        try{
            $input=$response.GetResponseStream();$output=[IO.File]::Open($download,[IO.FileMode]::CreateNew)
            try{
                $buffer=New-Object byte[] 65536;[long]$total=0
                while(($n=$input.Read($buffer,0,$buffer.Length)) -gt 0){
                    $total+=$n;if($total -gt $Update.bytes -or $total -gt 512MB -or $timer.Elapsed.TotalSeconds -gt 120){throw 'Update download exceeds declared size/time limit.'};$output.Write($buffer,0,$n)
                }
                if($total -ne $Update.bytes){throw 'Update download was truncated.'}
            }finally{$input.Dispose();$output.Dispose()}
        }finally{$response.Dispose()}
        $installed=Install-Chmod $download $ModsRoot
        if($installed.id -cne $Update.id -or $installed.version -cne $Update.version){throw 'Downloaded package ID/version differs from the author release.'}
        $previous=@(Get-InstalledChmods $ModsRoot|Where-Object{$_.manifest.id -ceq $Update.id -and $_.manifest.version -ceq $Update.installed})
        if($installed.extensions.Count -and ($previous.Count -ne 1 -or -not $previous[0].manifest.extensions.Count)){throw 'Update adds unsandboxed native code. Install and enable it manually after reviewing its declared capability.'}
        $selected=@($old.enabled|Where-Object {$_.id -ceq $Update.id -and $_.version -ceq $Update.installed})
        $next=@($old.enabled|ForEach-Object {
            if($_.id -ceq $Update.id -and $_.version -ceq $Update.installed){
                [pscustomobject]@{id=$installed.id;version=$installed.version}
            }else{$_}
        })
        if($selected.Count){
            $candidate=Resolve-Chmods $Game $ModsRoot $next -AllowCode:([bool]$old.allow_native_code)
            if($Executable -and $Renderer){Assert-ChmodLaunchCompatibility $candidate $Executable $Renderer}
            if($candidate.replacements.Count -or $candidate.uniforms.Count){
                if(-not $Prepare){throw 'Enabled asset updates require native preparation before selection is switched.'}
                if(-not $CacheRoot){$CacheRoot=Join-Path (Split-Path -Parent $PSScriptRoot) 'port/userdata/mod-cache'}
                $null=New-ChmodCache $Game $CacheRoot $candidate $Prepare
            }
        }
        # Keep a settings backup before atomic selection replacement. Failed
        # download/install/compatibility checks leave the prior selection intact.
        $backup=Join-Path ([IO.Path]::GetDirectoryName($Settings)) 'mods.previous.json'
        if ($selected.Count) {
            Write-ModJson $backup $old
            Write-ModJson $Settings ([ordered]@{version=1;enabled=$next;allow_native_code=([bool]$old.allow_native_code)}) $settingsHash
        }
        $committed=$true
        return $installed
    }finally{
        if([IO.File]::Exists($download)){[IO.File]::Delete($download)}
        if($installed -and -not $committed){
            $target=Get-ModPath $ModsRoot ($installed.id+'/'+$installed.version)
            if([IO.Directory]::Exists($target)){[IO.Directory]::Delete($target,$true)}
        }
    }
}

# Launcher-owned reversible activation of validated alternate banks in native saves.
function Get-ChmodRosterFiles([string]$Root) {
    if(-not [IO.Directory]::Exists($Root)){return}
    foreach($user in Get-ChildItem -LiteralPath $Root -Directory){
        if($user.Name -cnotmatch '^[0-9A-F]{16}$'){continue}
        $content=Get-ModPath $Root ($user.Name+'/54540818/00000001') -SavePath
        if(-not [IO.Directory]::Exists($content)){continue}
        foreach($package in Get-ChildItem -LiteralPath $content -Directory){
            if(-not $package.Name.EndsWith('.ROS',[StringComparison]::OrdinalIgnoreCase)){continue}
            if(-not $package.Name.EndsWith('.ROS',[StringComparison]::Ordinal)){throw 'Unsupported roster filename case: use native uppercase .ROS extension.'}
            $relative=$user.Name+'/54540818/00000001/'+$package.Name+'/'+$package.Name
            $header=$user.Name+'/54540818/Headers/00000001/'+$package.Name+'.header'
            $payloadPath=Get-ModPath $Root $relative -SavePath
            $headerPath=Get-ModPath $Root $header -SavePath
            if(-not [IO.File]::Exists($payloadPath) -or -not [IO.File]::Exists($headerPath)){throw "Incomplete native roster package: $($package.FullName)"}
            # SDK permits profile-neutral headers or the actual storage XUID.
            $h=[IO.File]::ReadAllBytes($headerPath)
            if($h.Length -ne 328){throw 'Unsupported roster content header size.'}
            $ownerOffset=if([BitConverter]::ToString($h[320..323]) -ceq '54-54-08-18'){312}else{308}
            $owner=([BitConverter]::ToString($h[$ownerOffset..($ownerOffset+7)])).Replace('-','')
            if($owner -cne '0000000000000000' -and $owner -cne $user.Name){throw 'Roster header XUID differs from its Dummy HDD profile.'}
            [pscustomobject]@{root=[IO.Path]::GetFullPath($Root);relative=$relative;header=$header;file=$payloadPath;header_file=$headerPath;name=$package.Name}
        }
    }
}
function Restore-ChmodRosterActivation([string]$Baseline,[string]$ProfileRoot,[string]$State) {
    $journal=Get-ModPath $State 'active.json'
    if(-not [IO.File]::Exists($journal)){return}
    $record=Read-ModJson $journal
    Assert-ModFields $record @('version','entries')
    if($record.version -ne 1 -or $record.entries -isnot [array] -or $record.entries.Count -gt 256){throw 'Invalid roster activation journal.'}
    # Preflight ALL entries before restoring any. A save modified after activation
    # belongs to the player; automatic rollback must never overwrite it.
    $restore=@()
    foreach($e in $record.entries){
        Assert-ModFields $e @('root','relative','header','header_sha256','before','after','backup')
        $root=[IO.Path]::GetFullPath($e.root)
        $base=[IO.Path]::GetFullPath($Baseline).TrimEnd('\')
        $profiles=[IO.Path]::GetFullPath($ProfileRoot).TrimEnd('\')
        if($root.TrimEnd('\') -ine $base -and ($root -notlike ($profiles+'\*') -or [IO.Path]::GetFileName($root) -cnotmatch '^[0-9a-f]{64}$' -or [IO.Path]::GetDirectoryName($root) -ine $profiles)){throw 'Roster journal root is outside known Dummy HDD storage.'}
        if($e.relative -cnotmatch '^[0-9A-F]{16}/54540818/00000001/([^/]+\.ROS)/\1$' -or $e.header -cne ($e.relative.Split('/')[0]+'/54540818/Headers/00000001/'+[IO.Path]::GetFileName($e.relative)+'.header')){throw 'Unsafe roster journal identity.'}
        foreach($hash in @($e.before,$e.after,$e.header_sha256)){Assert-ModText $hash '^[0-9a-f]{64}$'}
        $file=Get-ModPath $root $e.relative -SavePath; $header=Get-ModPath $root $e.header -SavePath
        $backup=Get-ModPath $State $e.backup -SavePath
        if((Get-ModHash $backup) -cne $e.before){throw 'Roster activation backup differs; original saves retained.'}
        $current=Get-ModHash $file
        if($current -cne $e.before -and $current -cne $e.after){throw "Roster changed after automatic jersey activation: $file. Preserve this save and its activation backup; automatic switching stopped to protect your edits."}
        if((Get-ModHash $header) -cne $e.header_sha256){throw 'Roster header changed after activation; switching stopped.'}
        if($current -ceq $e.after -and $e.after -cne $e.before){$restore+=[pscustomobject]@{file=$file;backup=$backup}}
    }
    foreach($e in $restore){
        $temp=$e.file+'.chmod-restore-'+[guid]::NewGuid().ToString('N')
        try{[IO.File]::Copy($e.backup,$temp);[IO.File]::Replace($temp,$e.file,[System.Management.Automation.Language.NullString]::Value)}finally{if([IO.File]::Exists($temp)){[IO.File]::Delete($temp)}}
    }
    # Keep backups and completed journal as an audit trail, never delete player saves.
    [IO.File]::Move($journal,(Get-ModPath $State ('completed-'+[guid]::NewGuid().ToString('N')+'.json')))
}
function Sync-ChmodRosterActivation([string]$Baseline,[string]$ProfileRoot,[string]$State,[string[]]$Roots,$Plan,[string]$VanillaGame) {
    $null=[IO.Directory]::CreateDirectory($State)
    Restore-ChmodRosterActivation $Baseline $ProfileRoot $State
    $required=@($Plan.uniforms|Where-Object{-not $_.selection -and $_.variant -ge 2}|ForEach-Object{
        $route=[ordered]@{artwork=$_.artwork;variant=$_.variant;required=$true}
        if($null -ne $_.neck_shape){$route.neck_shape=$_.neck_shape}
        $route
    })
    $alternates=@{}
    if($VanillaGame){
        $vanilla=Invoke-ModContract 'vanilla-uniforms' $VanillaGame 'unused'
        foreach($a in $vanilla.alternates){$alternates[([string]$a.artwork+':'+$a.variant)]=$a}
    }
    foreach($a in $required){$alternates[([string]$a.artwork+':'+$a.variant)]=$a}
    if(-not $alternates.Count -and -not $VanillaGame){return}
    $run=[guid]::NewGuid().ToString('N');$runRoot=Get-ModPath $State $run
    $null=[IO.Directory]::CreateDirectory($runRoot)
    $request=Get-ModPath $runRoot 'request.json';Write-ModJson $request ([ordered]@{unlock_existing=[bool]$VanillaGame;alternates=@($alternates.Values|Sort-Object artwork,variant)})
    $entries=@();$staged=@();$total=0L
    # Only the native .ROS package shape. Never inspect or edit Legacy/other saves.
    foreach($root in @($Roots|Select-Object -Unique)){
        foreach($r in Get-ChmodRosterFiles $root){
            if($entries.Count -ge 256){throw 'Automatic roster activation exceeds 256 saves.'}
            $total+=(Get-Item -LiteralPath $r.file).Length
            if($total -gt 1GB){throw 'Automatic roster activation exceeds 1 GiB.'}
            $dir=Get-ModPath $runRoot ([string]$entries.Count)
            $null=[IO.Directory]::CreateDirectory($dir)
            $output=Get-ModPath $dir ('output/'+$r.name) -SavePath
            $proof=Invoke-ModContract 'activate-roster-uniforms' $r.file $r.header_file @($request,$output)
            $backupRelative=$run+'/'+$entries.Count+'/original/'+$r.name
            $backup=Get-ModPath $State $backupRelative -SavePath
            $null=[IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($backup));[IO.File]::Copy($r.file,$backup)
            if((Get-ModHash $backup) -cne $proof.source_sha256){throw 'Roster changed during automatic activation preparation.'}
            $entries+=[ordered]@{root=$r.root;relative=$r.relative;header=$r.header;header_sha256=(Get-ModHash $r.header_file);before=$proof.source_sha256;after=$proof.output_sha256;backup=$backupRelative}
            $staged+=[pscustomobject]@{source=$output;target=$r.file;header=$r.header_file;entry=$entries[-1]}
        }
    }
    if(-not $entries.Count){if($required.Count){throw 'Additional alternate folders need an existing native Dummy HDD roster; create/save one first.'};return}
    Write-ModJson (Get-ModPath $State 'active.json') ([ordered]@{version=1;entries=@($entries)})
    try{
        foreach($s in $staged){
            if((Get-ModHash $s.target) -cne $s.entry.before -or (Get-ModHash $s.header) -cne $s.entry.header_sha256 -or (Get-ModHash $s.source) -cne $s.entry.after){throw 'Roster changed before activation commit.'}
            if($s.entry.before -ceq $s.entry.after){continue}
            $temp=$s.target+'.chmod-activate-'+[guid]::NewGuid().ToString('N')
            try{[IO.File]::Copy($s.source,$temp);[IO.File]::Replace($temp,$s.target,[System.Management.Automation.Language.NullString]::Value)}finally{if([IO.File]::Exists($temp)){[IO.File]::Delete($temp)}}
        }
    }catch{
        $failure=$_
        Restore-ChmodRosterActivation $Baseline $ProfileRoot $State
        throw $failure
    }
}
