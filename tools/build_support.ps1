# Interpreter detection is used only by source compilation, never by the beta runtime.
function Find-BuildPython {
    param([string]$Explicit, [string]$RepoRoot)
    $candidates = New-Object 'System.Collections.Generic.List[object]'
    if ($Explicit) {
        $command = Get-Command $Explicit -ErrorAction SilentlyContinue
        $resolved = if (Test-Path -LiteralPath $Explicit -PathType Leaf) { (Resolve-Path -LiteralPath $Explicit).Path } elseif ($command) { $command.Source } else { $Explicit }
        $candidates.Add(@($resolved, @()))
    } else {
        $candidates.Add(@((Join-Path $RepoRoot 'port/out/python-env/Scripts/python.exe'), @()))
        $py = Get-Command py.exe -ErrorAction SilentlyContinue
        if ($py) { $candidates.Add(@($py.Source, @('-3'))) }
        foreach ($command in @(Get-Command python.exe,python3.exe -All -ErrorAction SilentlyContinue)) { $candidates.Add(@($command.Source, @())) }
        foreach ($pattern in @('HKCU:/SOFTWARE/Python/PythonCore/*/InstallPath','HKLM:/SOFTWARE/Python/PythonCore/*/InstallPath')) {
            foreach ($key in @(Get-Item -Path $pattern -ErrorAction SilentlyContinue)) {
                $exe = $key.GetValue('ExecutablePath')
                if (-not $exe -and $key.GetValue('')) { $exe = Join-Path $key.GetValue('') 'python.exe' }
                if ($exe) { $candidates.Add(@($exe, @())) }
            }
        }
        foreach ($pattern in @("$env:LOCALAPPDATA/Programs/Python/Python*/python.exe",'C:/Python3*/python.exe')) {
            foreach ($file in @(Get-Item -Path $pattern -ErrorAction SilentlyContinue | Sort-Object FullName -Descending)) { $candidates.Add(@($file.FullName, @())) }
        }
    }
    foreach ($candidate in $candidates) {
        $exe = [string]$candidate[0]
        if (-not $exe -or $exe -match '\\Microsoft\\WindowsApps\\' -or -not (Test-Path -LiteralPath $exe -PathType Leaf)) { continue }
        $process = $null
        try {
            $info = New-Object Diagnostics.ProcessStartInfo
            $info.FileName = $exe
            $info.Arguments = (@($candidate[1]) + @('-c', '"import sys,json; print(json.dumps(dict(executable=sys.executable,valid=sys.version_info>=(3,11))))"')) -join ' '
            $info.UseShellExecute = $false; $info.CreateNoWindow = $true
            $info.RedirectStandardOutput = $true; $info.RedirectStandardError = $true
            $process = [Diagnostics.Process]::Start($info)
            $stdout = $process.StandardOutput.ReadToEndAsync(); $stderr = $process.StandardError.ReadToEndAsync()
            if (-not $process.WaitForExit(10000)) { $process.Kill(); $process.WaitForExit(); continue }
            if ($process.ExitCode -ne 0) { continue }
            $probe = $stdout.GetAwaiter().GetResult() | ConvertFrom-Json
            if ($probe.valid -and (Test-Path -LiteralPath $probe.executable -PathType Leaf)) { return [string]$probe.executable }
        } catch { }
        finally { if ($process) { $process.Dispose() } }
    }
    throw 'Source compilation needs Python 3.11+. A Windows Store execution alias is not an interpreter. Pass -PythonExecutable with the installed python.exe path, or install Python with the py launcher. The downloadable runnable beta does not need Python.'
}
function Find-BuildCommand {
    param([string]$Name, [string[]]$Candidates)
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    foreach ($pattern in $Candidates) {
        $file = Get-Item -Path $pattern -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($file) { return $file.FullName }
    }
    throw "Source compilation needs $Name. Install the documented C++ build prerequisites or download the runnable beta ZIP."
}

# Import the compiler/Windows SDK environment for double-clicked launchers and
# ordinary PowerShell terminals, not just Visual Studio developer prompts.
function Select-BuildVisualStudio($Instances) {
    foreach($instance in @($Instances|Sort-Object {[version]$_.installationVersion} -Descending)){
        $candidate=[string]$instance.installationPath
        $headers=@(Get-Item -Path (Join-Path $candidate 'VC/Tools/MSVC/*/include/vector') -ErrorAction SilentlyContinue)
        if($headers.Count -and (Test-Path -LiteralPath (Join-Path $candidate 'VC/Auxiliary/Build/vcvars64.bat'))){return $candidate}
    }
    return $null
}
function Initialize-BuildToolchain {
    if (-not [Environment]::Is64BitProcess -or $env:PROCESSOR_ARCHITECTURE -ne 'AMD64') {
        throw 'Source compilation requires Windows x64 on an Intel/AMD PC. Use the Windows x64 build host; Wine/macOS/ARM builds are not validated.'
    }
    $vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
    $installation = $null
    if (Test-Path -LiteralPath $vswhere) {
        # New VS releases can rename component IDs. Query all installations and
        # inspect the actual x64 toolset instead of excluding a valid newer SDK.
        $instances=& $vswhere -all -products '*' -format json|ConvertFrom-Json
        $installation=Select-BuildVisualStudio $instances
    }
    if ($installation) {
        $vcvars = Join-Path $installation 'VC/Auxiliary/Build/vcvars64.bat'
        if (-not (Test-Path -LiteralPath $vcvars)) { throw 'Visual Studio C++ tools are incomplete. Repair Desktop development with C++ and the Windows SDK in Visual Studio Installer.' }
        $info=New-Object Diagnostics.ProcessStartInfo
        $info.FileName=Join-Path $env:SystemRoot 'System32\cmd.exe'
        $info.Arguments='/d /c call "'+$vcvars+'" >nul && set'
        $info.UseShellExecute=$false;$info.CreateNoWindow=$true
        $info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
        $setup=[Diagnostics.Process]::Start($info)
        try {
            $output=$setup.StandardOutput.ReadToEndAsync();$errors=$setup.StandardError.ReadToEndAsync()
            if(-not $setup.WaitForExit(30000)){ $setup.Kill();throw 'Visual Studio environment setup timed out. Repair the C++ tools installation.' }
            if($setup.ExitCode -ne 0){throw "Visual Studio x64 environment setup failed: $($errors.GetAwaiter().GetResult())"}
            $environment=$output.GetAwaiter().GetResult() -split '\r?\n'
        }finally{$setup.Dispose()}
        foreach ($line in $environment) {
            if ($line -match '^([^=]+)=(.*)$') { [Environment]::SetEnvironmentVariable($matches[1],$matches[2],'Process') }
        }
    }
    if (-not $env:VCToolsInstallDir -or -not $env:WindowsSdkDir -or -not (Test-Path -LiteralPath (Join-Path $env:VCToolsInstallDir 'include/vector'))) {
        throw 'Microsoft C++ headers and Windows SDK are missing. Install Visual Studio 2022/2026 Build Tools: Desktop development with C++, MSVC x64/x86 tools and Windows 10/11 SDK. Then rerun this command; no developer terminal is needed.'
    }
    $cmakeCandidates=@('C:/Program Files/CMake/bin/cmake.exe')
    $clangCandidates=@('C:/Program Files/LLVM/bin/clang++.exe')
    $ninjaCandidates=@("$env:LOCALAPPDATA/Microsoft/WinGet/Packages/Ninja-build.Ninja_*/ninja.exe")
    if ($installation) {
        $cmakeCandidates+=Join-Path $installation 'Common7/IDE/CommonExtensions/Microsoft/CMake/CMake/bin/cmake.exe'
        $ninjaCandidates+=Join-Path $installation 'Common7/IDE/CommonExtensions/Microsoft/CMake/Ninja/ninja.exe'
        $clangCandidates+=Join-Path $installation 'VC/Tools/Llvm/x64/bin/clang++.exe'
    }
    $cmake=Find-BuildCommand 'cmake.exe' $cmakeCandidates
    $clang=Find-BuildCommand 'clang++.exe' $clangCandidates
    $ninja=Find-BuildCommand 'ninja.exe' $ninjaCandidates
    $git=Find-BuildCommand 'git.exe' @('C:/Program Files/Git/cmd/git.exe')
    $cmakeVersion=(& $cmake --version | Select-Object -First 1)
    $clangVersion=(& $clang --version | Select-Object -First 1)
    if ($cmakeVersion -notmatch '(\d+\.\d+\.\d+)' -or [version]$matches[1] -lt [version]'3.25.0') { throw "CMake 3.25+ is required; detected: $cmakeVersion" }
    if ($clangVersion -notmatch 'version (\d+)' -or [int]$matches[1] -lt 20) { throw "Clang 20+ is required; detected: $clangVersion. Install current LLVM and reopen PowerShell." }
    foreach ($tool in @($cmake,$clang,$ninja,$git)) { $env:PATH=(Split-Path -Parent $tool)+';'+$env:PATH }
    [pscustomobject]@{cmake=$cmake;clang=$clang;ninja=$ninja;git=$git;visual_studio=$installation;vc_tools=$env:VCToolsInstallDir;windows_sdk=$env:WindowsSdkDir;cmake_version=$cmakeVersion;clang_version=$clangVersion}
}

function Test-BuildCompiler([string]$Compiler) {
    $folder=Join-Path (Split-Path -Parent $global:Ch2k8BuildContext.log) 'compiler-probe'
    $null=New-Item -ItemType Directory -Path $folder -Force
    $source=Join-Path $folder 'toolchain.cpp';$program=Join-Path $folder 'toolchain.exe'
    @'
#include <windows.h>
#include <string>
#include <iostream>
int main(int argc,char** argv) {
 std::string value=argc>1?argv[1]:"probe/path";
 std::cout << value.find_first_of("/\\") << ":" << value.find_last_of("/\\") << ":" << GetCurrentProcessId() << "\n";
 return 0;
}
'@ | Set-Content -LiteralPath $source -Encoding ASCII
    Invoke-BuildCommand 'compiler-probe' $Compiler @('-std=c++23','-O2','-DNDEBUG','-fms-runtime-lib=dll',$source,'-o',$program) 'The compiler cannot compile/link a Windows C++ program. Repair/update the Microsoft C++ tools and Windows SDK. Undefined __std_* symbols usually indicate mixed Microsoft STL headers/libraries; use the newest complete installed toolset.'
    Invoke-BuildCommand 'compiler-runtime' $program @() 'The compiled probe could not run. Repair/install the x64 Microsoft C++ redistributable matching your build tools, then retry.'
}

function Write-BuildStatus {
    param([string]$Stage,[string]$State='running',[string]$Message='',[string]$Recovery='',[int]$ExitCode=0)
    if (-not $global:Ch2k8BuildContext) { return }
    $context=$global:Ch2k8BuildContext
    $context.stage=$Stage
    $report=@{format=1;stage=$Stage;state=$State;message=$Message;recovery=$Recovery;exit_code=$ExitCode;log=$context.log;source=$context.source;updated_utc=[DateTime]::UtcNow.ToString('o')}
    $temporary=$context.status+'.tmp'
    $report|ConvertTo-Json -Depth 6|Set-Content -LiteralPath $temporary -Encoding UTF8
    Move-Item -LiteralPath $temporary -Destination $context.status -Force
    if ($Message) { Write-BuildMessage "[$Stage] $Message" }
}
function Write-BuildMessage([string]$Message) {
    Write-Host $Message
    if ($global:Ch2k8BuildContext) { [IO.File]::AppendAllText($global:Ch2k8BuildContext.log,$Message+[Environment]::NewLine) }
}
function ConvertTo-BuildArgument([string]$Value) {
    if ($Value.Contains('"')) { throw 'Build arguments cannot contain double quotes.' }
    '"'+($Value -replace '(\\+)$','$1$1')+'"'
}

# Read both native streams concurrently. PowerShell 5.1 can otherwise treat a
# compiler's successful stderr output as a terminating NativeCommandError.
function Invoke-BuildCommand {
    param([string]$Stage,[string]$Executable,[string[]]$Arguments,[string]$Recovery='Read the final compiler error below. Correct the cause and rerun the same build; completed stages are reused.')
    Write-BuildStatus $Stage -Message 'Running'
    Write-BuildMessage (($Executable+' '+(($Arguments|ForEach-Object{ConvertTo-BuildArgument $_}) -join ' ')))
    if (-not ('Ch2k8BuildProcess' -as [type])) {
        Add-Type -TypeDefinition @'
using System;
using System.Collections.Concurrent;
using System.Diagnostics;
public sealed class Ch2k8BuildProcess : IDisposable {
 public readonly ConcurrentQueue<string> Lines = new ConcurrentQueue<string>();
 public readonly ConcurrentQueue<string> Errors = new ConcurrentQueue<string>();
 public readonly Process Process = new Process();
 public Ch2k8BuildProcess(string executable, string arguments, string directory) {
  Process.StartInfo = new ProcessStartInfo(executable,arguments) { WorkingDirectory=directory,UseShellExecute=false,CreateNoWindow=true,RedirectStandardOutput=true,RedirectStandardError=true };
  Process.StartInfo.StandardOutputEncoding = System.Text.Encoding.UTF8;
  Process.StartInfo.StandardErrorEncoding = System.Text.Encoding.UTF8;
  Process.StartInfo.EnvironmentVariables["PYTHONUTF8"] = "1";
  Process.OutputDataReceived += (sender,e) => { if(e.Data!=null) Lines.Enqueue(e.Data); };
  Process.ErrorDataReceived += (sender,e) => { if(e.Data!=null) { Lines.Enqueue(e.Data); Errors.Enqueue(e.Data); string old; while(Errors.Count>18) Errors.TryDequeue(out old); } };
  Process.Start(); Process.BeginOutputReadLine(); Process.BeginErrorReadLine();
 }
 public void Dispose() { Process.Dispose(); }
}
'@
    }
    $process=New-Object Ch2k8BuildProcess($Executable,(($Arguments|ForEach-Object{ConvertTo-BuildArgument $_}) -join ' '),(Get-Location).ProviderPath)
    $tail=New-Object 'System.Collections.Generic.Queue[string]'
    try {
        do {
            $finished=$process.Process.WaitForExit(200)
            $line=''
            while($process.Lines.TryDequeue([ref]$line)) { Write-BuildMessage $line; $tail.Enqueue($line);if($tail.Count -gt 18){$null=$tail.Dequeue()} }
        } while(-not $finished)
        $process.Process.WaitForExit()
        $line='';while($process.Lines.TryDequeue([ref]$line)){Write-BuildMessage $line;$tail.Enqueue($line);if($tail.Count -gt 18){$null=$tail.Dequeue()}}
        if($process.Process.ExitCode -ne 0) {
            $detail=($tail.ToArray() -join [Environment]::NewLine)
            if($process.Errors.Count){$detail+=[Environment]::NewLine+'Standard error:'+[Environment]::NewLine+($process.Errors.ToArray() -join [Environment]::NewLine)}
            Write-BuildStatus $Stage 'failed' $detail $Recovery $process.Process.ExitCode
            throw "$Stage failed (exit $($process.Process.ExitCode)). $Recovery`n$detail"
        }
    } finally { $process.Dispose() }
}
