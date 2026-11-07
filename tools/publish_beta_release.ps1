<# Publish the verified runnable beta asset; credentials are never printed or saved. #>
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Package,
    [Parameter(Mandatory=$true)][ValidatePattern('^[a-f0-9]{40}$')][string]$TargetCommit,
    [Parameter(Mandatory=$true)][string]$NotesFile,
    [ValidatePattern('^[A-Za-z0-9._-]+$')][string]$Tag='ZMO-beta1',
    [switch]$Publish
)
$ErrorActionPreference='Stop'
Import-Module (Join-Path $PSHOME 'Modules/Microsoft.PowerShell.Utility')
$Package=(Resolve-Path -LiteralPath $Package).Path
if([IO.Path]::GetExtension($Package) -ine '.zip'){throw 'Publish the verified beta ZIP.'}
$notes=[IO.File]::ReadAllText((Resolve-Path -LiteralPath $NotesFile).Path)
$credentials=@{}
@('protocol=https','host=github.com','') | & git credential fill 2>$null | ForEach-Object {
    if($_ -match '^([^=]+)=(.*)$'){$credentials[$matches[1]]=$matches[2]}
}
if(-not $credentials.password){throw 'GitHub Git credentials are unavailable.'}
$headers=@{Authorization='Bearer '+$credentials.password;Accept='application/vnd.github+json';'User-Agent'='CH2K8-beta-maintenance';'X-GitHub-Api-Version'='2022-11-28'}
$base='https://api.github.com/repos/kima1810/CH2K8-decomp'
$release=$null
try{$release=Invoke-RestMethod -Uri "$base/releases/tags/$Tag" -Headers $headers}catch{if([int]$_.Exception.Response.StatusCode -ne 404){throw}}
if(-not $release){
    $body=@{tag_name=$Tag;target_commitish=$TargetCommit;name="$Tag - Windows x64";body=$notes;draft=$true;prerelease=$true}|ConvertTo-Json
    $release=Invoke-RestMethod -Uri "$base/releases" -Headers $headers -Method Post -Body $body -ContentType 'application/json'
}
$name=[IO.Path]::GetFileName($Package)
if(@($release.assets|Where-Object{$_.name -eq $name}).Count){throw 'An asset with this name already exists. Use a new revision filename; existing assets were preserved.'}
$upload='https://uploads.github.com/repos/kima1810/CH2K8-decomp/releases/'+$release.id+'/assets?name='+[Uri]::EscapeDataString($name)
$asset=Invoke-RestMethod -Uri $upload -Headers $headers -Method Post -InFile $Package -ContentType 'application/zip'
$checksum=$Package+'.sha256'
((Get-FileHash -LiteralPath $Package -Algorithm SHA256).Hash.ToLowerInvariant()+'  '+$name)|Set-Content -LiteralPath $checksum -Encoding ASCII
$sumUpload='https://uploads.github.com/repos/kima1810/CH2K8-decomp/releases/'+$release.id+'/assets?name='+[Uri]::EscapeDataString($name+'.sha256')
$null=Invoke-RestMethod -Uri $sumUpload -Headers $headers -Method Post -InFile $checksum -ContentType 'text/plain'
if($Publish){
    $body=@{draft=$false;prerelease=$true;body=$notes;name="$Tag - Windows x64"}|ConvertTo-Json
    $release=Invoke-RestMethod -Uri "$base/releases/$($release.id)" -Headers $headers -Method Patch -Body $body -ContentType 'application/json'
}
@{release=$release.html_url;asset=$asset.browser_download_url;draft=$release.draft;sha256=(Get-FileHash -LiteralPath $Package).Hash.ToLowerInvariant()}|ConvertTo-Json
$credentials.Clear();$headers.Clear()
