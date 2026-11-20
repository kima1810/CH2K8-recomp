# Existing launcher child view; uses the same backend as the CLI/tests.
function Show-ChmodView($Owner, [string]$Game, [string]$ModsRoot, [string]$Settings, [string]$PreviewOutput, [string]$Executable, [string]$Renderer) {
    $dialog=New-Object System.Windows.Forms.Form
    $dialog.Text='CH2K8 Mods'
    $dialog.AllowDrop=$true
    $dialog.ClientSize=New-Object Drawing.Size(900,670)
    $dialog.MinimumSize=$dialog.Size
    $dialog.StartPosition='CenterParent'
    $searchLabel=New-Object System.Windows.Forms.Label
    $searchLabel.Text='Find mods'
    $searchLabel.SetBounds(12,16,70,23)
    $dialog.Controls.Add($searchLabel)
    $search=New-Object System.Windows.Forms.TextBox
    $search.SetBounds(85,12,335,24)
    $dialog.Controls.Add($search)
    $summary=New-Object System.Windows.Forms.Label
    $summary.SetBounds(435,16,445,24)
    $dialog.Controls.Add($summary)
    $list=New-Object System.Windows.Forms.ListView
    $list.View='Details'; $list.FullRowSelect=$true; $list.MultiSelect=$false; $list.HideSelection=$false; $list.SetBounds(12,44,876,250); $list.Anchor="Top,Left,Right"
    $null=$list.Columns.Add('Mod',300)
    $null=$list.Columns.Add('State',150)
    $null=$list.Columns.Add('Version',100)
    $null=$list.Columns.Add('Author',285)
    $dialog.Controls.Add($list)
    $message=New-Object System.Windows.Forms.TextBox; $message.Multiline=$true; $message.ReadOnly=$true; $message.ScrollBars='Vertical'; $message.SetBounds(12,578,876,78); $message.Anchor='Top,Bottom,Left,Right'
    $message.Text='Select a mod to see its details, or check the enabled selection before launching.'
    $dialog.Controls.Add($message)
    $details=New-Object System.Windows.Forms.TextBox
    $details.Multiline=$true
    $details.ReadOnly=$true
    $details.ScrollBars='Vertical'
    $details.SetBounds(12,380,876,105)
    $details.Anchor='Top,Left,Right'
    $dialog.Controls.Add($details)
    $rosterLabel=New-Object System.Windows.Forms.Label
    $rosterLabel.SetBounds(12,493,876,37)
    $dialog.Controls.Add($rosterLabel)
    $state=@{enabled=@();installed=@();update=$null;allow_native_code=$false;updating=$false;settingsHash=$null}
    $buttons=@{}
    $nativeOptIn=New-Object System.Windows.Forms.CheckBox
    $nativeOptIn.Text='Allow native DLL mods to run with full user access'
    $nativeOptIn.SetBounds(12,536,876,30)
    $dialog.Controls.Add($nativeOptIn)
    $showDetails={
        $item=if($list.SelectedItems.Count){$list.SelectedItems[0].Tag}
        $manifest=if($item){$item.manifest}
        $position=if($item){$item.priority}else{-1}
        $canToggle=$manifest -or ($item -and $item.members.Count) -or $position -ge 0
        $buttons['toggle'].Enabled=[bool]$canToggle
        $buttons['toggle'].Text=if($item.group){if($item.allEnabled){'Disable folder'}else{'Enable folder'}}elseif($position -ge 0){'Disable'}else{'Enable'}
        $buttons['higher'].Enabled=($position -ge 0 -and $position -lt $state.enabled.Count-1)
        $buttons['lower'].Enabled=($position -gt 0)
        $buttons['checkUpdate'].Enabled=[bool]($manifest -and $manifest.update_source)
        $buttons['installUpdate'].Enabled=[bool]($manifest -and $state.update -and
            $state.update.id -ceq $manifest.id -and $state.update.installed -ceq $manifest.version)
        if (-not $item) {
            $details.Text='Select an installed mod to inspect its requirements and priority.'
        } elseif ($item.group) {
            $details.Text="$($item.members.Count) packages in $($item.group). Select a child row to manage it individually."
        } elseif (-not $manifest) {
            $details.Text=$item.error + [Environment]::NewLine + $item.root
        } else {
            $deps=@($manifest.dependencies | ForEach-Object { "$($_.id) $($_.version)" })
            $missing=@($manifest.dependencies | Where-Object {
                $dependency=$_
                -not @($state.enabled | Where-Object { $_.id -ceq $dependency.id -and $_.version -ceq $dependency.version }).Count
            } | ForEach-Object { "$($_.id) $($_.version)" })
            $lines=@(
                "$($manifest.name) $($manifest.version) ($($manifest.id))"
                "Content $($manifest.content -join ', ') | API $($manifest.requires.mod_api) | $($manifest.capabilities -join ', ')"
                "Requires $(if($deps.Count){$deps -join ', '}else{'no other mods'})"
            )
            if($missing.Count){$lines+="Enable these dependencies first: $($missing -join ', ')"}
            if($manifest.incompatible.Count){$lines+="Incompatible with $($manifest.incompatible -join ', ')"}
            if($manifest.extensions.Count -and -not $state.allow_native_code){$lines+='Enable native DLL permission to use this mod.'}
            if($manifest.assets.Count -or $manifest.uniforms.Count){$lines+='Renderer requirement: Direct3D 12'}
            if($manifest.update_source){$lines+='Author updates available through Check update.'}
            $details.Text=$lines -join [Environment]::NewLine
        }
    }
    if ([IO.File]::Exists($Settings)) {
        $state.settingsHash=Get-ModHash $Settings
        $saved=Read-ModJson $Settings
        Assert-ChmodSettings $saved
        $state.enabled=@($saved.enabled)
        $state.allow_native_code=($saved.allow_native_code -eq $true)
    }
    $nativeOptIn.Checked=$state.allow_native_code
    $renderList={
        $selectedKey=if($list.SelectedItems.Count){$list.SelectedItems[0].Tag.key}
        $list.BeginUpdate()
        try {
            $list.Items.Clear()
            $items=@()
            $seen=@{}
            foreach($entry in $state.installed){
                $m=$entry.manifest
                $key=if($m){"$($m.id)/$($m.version)"}else{$entry.root}
                $items += [pscustomobject]@{
                    manifest=$m;root=$entry.root;error=$entry.error;key=$key
                    name=if($m){$m.name}else{[IO.Path]::GetFileName($entry.root)}
                    author=if($m){$m.author}else{''}
                    version=if($m){$m.version}else{''}
                    priority=-1
                }
                if($m){$seen[$key]=$items[-1]}
            }
            for($i=0;$i -lt $state.enabled.Count;$i++){
                $active=$state.enabled[$i]
                $key="$($active.id)/$($active.version)"
                if($seen.ContainsKey($key)){$seen[$key].priority=$i}
                else {
                    $items += [pscustomobject]@{
                        manifest=$null;root='';error='This enabled version is missing or invalid. Disable it or reinstall the package.'
                        key=$key;name=$active.id;author='';version=$active.version;priority=$i
                    }
                }
            }
            $groups=@{}
            foreach($entry in $state.installed){
                if(-not $entry.manifest -or -not $entry.relative){continue}
                $parent=Split-Path -Path $entry.relative -Parent
                while($parent){
                    $key=$parent.Replace('\','/')
                    if(-not $groups.ContainsKey($key)){$groups[$key]=@()}
                    $groups[$key]+=$entry.manifest
                    $parent=Split-Path -Path $parent -Parent
                }
            }
            foreach($group in ($groups.Keys | Sort-Object)){
                $members=@($groups[$group] | Group-Object id | ForEach-Object {
                    $_.Group | Sort-Object { [version]$_.version } -Descending | Select-Object -First 1
                })
                $enabled=@($members | Where-Object {$m=$_; @($state.enabled | Where-Object {$_.id -ceq $m.id -and $_.version -ceq $m.version}).Count})
                $items+=[pscustomobject]@{key='group:'+ $group;name='Folder: '+$group;group=$group;members=$members;
                    allEnabled=($enabled.Count -eq $members.Count);enabledCount=$enabled.Count;priority=-1;version='';author=''}
            }
            $filter=$search.Text.Trim()
            foreach($item in ($items | Sort-Object @{Expression={$_.priority -lt 0}},@{Expression={$_.priority};Descending=$true},name,version)){
                if($filter -and "$($item.name) $($item.author) $($item.key)".IndexOf($filter,[StringComparison]::OrdinalIgnoreCase) -lt 0){continue}
                $status=if($item.group){"$($item.enabledCount)/$($item.members.Count) enabled"}elseif($item.error){
                    if($item.priority -ge 0){'Enabled - broken'}else{'Invalid package'}
                }elseif($item.priority -ge 0){"Enabled / $($item.priority+1)"}else{'Disabled'}
                $row=New-Object System.Windows.Forms.ListViewItem($item.name)
                foreach($value in @($status,$item.version,$item.author)){$null=$row.SubItems.Add([string]$value)}
                $row.Tag=$item
                $null=$list.Items.Add($row)
                if($item.key -ceq $selectedKey){$row.Selected=$true;$row.Focused=$true;$row.EnsureVisible()}
            }
        } finally {$list.EndUpdate()}
        $invalid=@($state.installed | Where-Object error).Count
        $summary.Text="$($state.enabled.Count) enabled | $($state.installed.Count) found | $invalid invalid"
        & $showDetails
    }
    $refresh={
        param([switch]$KeepInstalled)
        if(-not $KeepInstalled){$state.installed=@(Get-InstalledChmods $ModsRoot -IncludeInvalid)}
        & $renderList
        $rosters=@($state.installed|Where-Object {$m=$_.manifest;$m.roster -and @($state.enabled|Where-Object {$_.id -ceq $m.id -and $_.version -ceq $m.version}).Count})
        $rosterLabel.Text=if($rosters.Count){'Next launch uses the isolated roster profile for '+(($rosters|ForEach-Object{$_.manifest.name+' '+$_.manifest.version}) -join ', ')+'.'}else{'Next launch uses the baseline save profile.'}
        $nativeSelected=@($state.installed|Where-Object{$m=$_.manifest;$m.extensions.Count -and @($state.enabled|Where-Object{$_.id -ceq $m.id -and $_.version -ceq $m.version}).Count})
        if(-not $rosters.Count -and $nativeSelected.Count){$rosterLabel.Text='Next launch uses an isolated save profile for the enabled native DLL mods.'}
    }
    $state.saved_enabled=@($state.enabled)
    $persist={
        try {
            if (-not $state.settingsHash -and [IO.File]::Exists($Settings)) {
                throw 'Mod settings changed in another launcher. Reopen Mods to reload them.'
            }
            Write-ModJson $Settings ([ordered]@{version=1;enabled=@($state.enabled);allow_native_code=$state.allow_native_code}) $state.settingsHash
        }
        catch{$state.enabled=@($state.saved_enabled);throw}
        $state.settingsHash=Get-ModHash $Settings
        $state.saved_enabled=@($state.enabled)
        & $refresh -KeepInstalled
    }
    $nativeOptIn.Add_CheckedChanged({
        if($state.updating){return}
        $previous=$state.allow_native_code
        try{$state.allow_native_code=[bool]$nativeOptIn.Checked; & $persist}
        catch{
            $state.allow_native_code=$previous;$state.updating=$true
            try{$nativeOptIn.Checked=$previous}finally{$state.updating=$false}
            $message.Text='Could not save native-code permission: '+$_.Exception.Message
        }
    })
    $checkSelection={
        param([object[]]$Selection)
        $message.Text='Checking enabled mods and source assets...'
        $message.Refresh()
        $plan=Resolve-Chmods $Game $ModsRoot $Selection -AllowCode:$state.allow_native_code
        if($Executable -and $Renderer){Assert-ChmodLaunchCompatibility $plan $Executable $Renderer}
        if($Renderer -eq 'vulkan' -and [IO.File]::Exists((Join-Path $Game 'assets.json'))){
            throw 'This Xbox loose-resource installation requires Direct3D 12. Change the renderer in the launcher.'
        }
        return $plan
    }
    $saveSelection={
        param([object[]]$Selection,$Plan,[string]$Status)
        $state.enabled=@($Selection)
        & $persist
        $message.Text=$Status
        if($Plan -and $Plan.conflicts.Count){$message.AppendText([Environment]::NewLine+($Plan.conflicts -join [Environment]::NewLine))}
    }
    $installFolder={
        param([string]$Path)
        $receipt=Install-Chmod $Path $ModsRoot -ModFolder
        $message.Text=if($receipt.packages){"Installed $($receipt.packages) packages in $($receipt.name)."}else{"Installed $($receipt.name)."}
        & $refresh
    }
    $dragEnter={
        if($_.Data.GetDataPresent([Windows.Forms.DataFormats]::FileDrop)){ $_.Effect=[Windows.Forms.DragDropEffects]::Copy }
    }
    $dragDrop={
        try {
            foreach($path in $_.Data.GetData([Windows.Forms.DataFormats]::FileDrop)){& $installFolder $path}
        } catch {$message.Text=$_.Exception.Message}
    }
    $list.AllowDrop=$true
    foreach($surface in @($dialog,$list)){
        $surface.Add_DragEnter($dragEnter)
        $surface.Add_DragDrop($dragDrop)
    }
    $actions=@(
        @('install','Import legacy archive', {
            $picker=New-Object System.Windows.Forms.OpenFileDialog; $picker.Filter='CHMOD package (*.chmod)|*.chmod'
            try { if($picker.ShowDialog($dialog) -eq 'OK') { $m=Install-Chmod $picker.FileName $ModsRoot; $message.Text="Installed $($m.name) $($m.version). Enable it to select this version; the previous version is retained."; & $refresh } } finally { $picker.Dispose() }
        }),
        @('import','Install mod or collection', {
            $picker=New-Object System.Windows.Forms.FolderBrowserDialog
            try { if($picker.ShowDialog($dialog) -eq 'OK') { & $installFolder $picker.SelectedPath } } finally { $picker.Dispose() }
        }),
        @('toggle','Enable', {
            $item=$list.SelectedItems[0].Tag
            if($item.group){
                $members=@($item.members)
                if($item.allEnabled -or $item.enabledCount -eq $members.Count){
                    $keys=@($item.members | ForEach-Object {"$($_.id)/$($_.version)"})
                    $next=@($state.enabled | Where-Object {"$($_.id)/$($_.version)" -cnotin $keys})
                }else{
                    $ids=@($members.id)
                    $next=@($state.enabled | Where-Object {$_.id -cnotin $ids})
                    $next+=@($members | Sort-Object id | ForEach-Object {[pscustomobject]@{id=$_.id;version=$_.version}})
                }
                & $saveSelection -Selection $next -Status 'Folder selection saved. Use Check selection to validate dependencies.'
                return
            }
            if($item.priority -ge 0){
                $next=@(for($i=0;$i -lt $state.enabled.Count;$i++){if($i -ne $item.priority){$state.enabled[$i]}})
                & $saveSelection -Selection $next -Status 'Disabled for the next launch. Use Check selection to review remaining dependencies.'
                return
            }
            $m=$item.manifest
            $next=@(for($i=0;$i -lt $state.enabled.Count;$i++){
                if($state.enabled[$i].id -ceq $m.id){[pscustomobject]@{id=$m.id;version=$m.version}}
                else{$state.enabled[$i]}
            })
            if(-not @($next | Where-Object { $_.id -ceq $m.id }).Count){
                $next += [pscustomobject]@{id=$m.id;version=$m.version}
            }
            & $saveSelection -Selection $next -Status 'Enabled for the next launch. Use Check selection to validate compatibility now.'
        }),
        @('higher','Higher priority', {
            $index=$list.SelectedItems[0].Tag.priority
            $next=@($state.enabled)
            $next[$index],$next[$index+1]=$next[$index+1],$next[$index]
            & $saveSelection -Selection $next -Status 'Priority saved. Use Check selection to review overlaps.'
        }),
        @('lower','Lower priority', {
            $index=$list.SelectedItems[0].Tag.priority
            $next=@($state.enabled)
            $next[$index],$next[$index-1]=$next[$index-1],$next[$index]
            $plan=& $checkSelection -Selection $next
            & $saveSelection -Selection $next -Plan $plan -Status 'Priority saved.'
        }),
        @('validate','Check selection', {
            if(-not $state.enabled.Count){$message.Text='No mods are enabled.';return}
            $plan=& $checkSelection -Selection $state.enabled
            $message.Text="$($plan.active.Count) enabled mods passed preflight. Game assets are prepared when you launch."
            if($plan.conflicts.Count){$message.AppendText([Environment]::NewLine+($plan.conflicts -join [Environment]::NewLine))}
        }),
        @('reset','Disable all', {
            & $saveSelection -Selection @() -Status 'All mods disabled for the next launch. Installed versions are still available.'
        }),
        @('checkUpdate','Check update', {
            if(-not $list.SelectedItems.Count){return}; $m=$list.SelectedItems[0].Tag.manifest
            $state.update=Get-ChmodUpdate $m
            if((Compare-ModVersion $state.update.version $m.version) -le 0){
                $state.update=$null
                $message.Text='This version is current.'
            }else{
                $message.Text="Version $($state.update.version) is available. Install update retains the older package."
            }
        }),
        @('installUpdate','Install update', {
            if(-not $state.update){throw 'Select a mod and Check update first.'}
            if(-not $list.SelectedItems.Count -or $list.SelectedItems[0].Tag.manifest.id -cne $state.update.id){throw 'Select the mod whose update was checked.'}
            if(Get-Process ch2k8 -ErrorAction SilentlyContinue){throw 'Close the game before installing an update.'}
            $m=Install-ChmodUpdate $state.update $ModsRoot $Game $Settings `
                {param($folder) Invoke-Ch2k8Preparation $folder -Interactive} `
                -CacheRoot (Join-Path (Split-Path -Parent $Settings) 'mod-cache') -Executable $Executable -Renderer $Renderer
            if([IO.File]::Exists($Settings)){
                $state.settingsHash=Get-ModHash $Settings
                $saved=Read-ModJson $Settings
                $state.enabled=@($saved.enabled)
                $state.saved_enabled=@($state.enabled)
                $state.allow_native_code=($saved.allow_native_code -eq $true)
                $state.updating=$true
                try{$nativeOptIn.Checked=$state.allow_native_code}finally{$state.updating=$false}
            }
            $state.update=$null
            & $refresh
            $message.Text="Installed $($m.name) $($m.version). Use Enable to switch between installed versions."
        })
    )
    for($i=0;$i -lt $actions.Count;$i++) {
        $button=New-Object System.Windows.Forms.Button; $button.Text=$actions[$i][1]; $button.SetBounds((12+($i%6)*146),(305+36*[Math]::Floor($i/6)),140,30)
        $buttons[$actions[$i][0]]=$button
        # Keep the handler in the button, not a loop variable captured into a
        # dynamic module. The original dialog/script scope owns backend helpers
        # and view state throughout ShowDialog; GetNewClosure breaks that scope.
        $button.Tag=$actions[$i][2]
        $button.Add_Click({
            param($sender,$eventArgs)
            try { $handler=$sender.Tag; & $handler }
            catch {
                $message.Text=$_.Exception.Message
                try {
                    $log=[IO.Path]::ChangeExtension($Settings,'.ui-error.log')
                    [IO.File]::AppendAllText($log,([DateTime]::UtcNow.ToString('o')+' '+$sender.Text+"`r`n"+$_.ToString()+"`r`n"+$_.ScriptStackTrace+"`r`n"))
                }catch{}
            } finally { & $showDetails }
        })
        $dialog.Controls.Add($button)
    }
    $search.Add_TextChanged({ & $renderList })
    $list.Add_SelectedIndexChanged({ & $showDetails })
    $close=New-Object System.Windows.Forms.Button
    $close.Text='Close'
    $close.SetBounds(748,341,140,30)
    $close.Anchor='Top,Right'
    $close.DialogResult=[System.Windows.Forms.DialogResult]::Cancel
    $dialog.CancelButton=$close
    $dialog.Controls.Add($close)
    & $refresh
    try {
        if ($PreviewOutput) {
            $dialog.Show(); [System.Windows.Forms.Application]::DoEvents()
            $bitmap=New-Object Drawing.Bitmap($dialog.Width,$dialog.Height)
            try {
                $dialog.DrawToBitmap($bitmap,(New-Object Drawing.Rectangle(0,0,$dialog.Width,$dialog.Height)))
                $bitmap.Save([IO.Path]::GetFullPath($PreviewOutput),[Drawing.Imaging.ImageFormat]::Png)
            } finally { $bitmap.Dispose() }
        } else { $null=$dialog.ShowDialog($Owner) }
    } finally { $dialog.Dispose() }
}
