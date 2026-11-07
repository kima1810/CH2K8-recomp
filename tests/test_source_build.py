"""Source-checkout setup regressions from tester reports."""
import hashlib,json,os,shutil,subprocess,sys
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]
SHELL=shutil.which('powershell.exe')
pytestmark=pytest.mark.skipif(not SHELL,reason='Windows PowerShell required')


def test_installed_python_is_resolved_to_real_executable(tmp_path):
    wrapper=tmp_path/'probe.ps1'
    wrapper.write_text('''param($Support,$Interpreter,$Root)
$ErrorActionPreference='Stop'
Import-Module (Join-Path $PSHOME 'Modules/Microsoft.PowerShell.Utility')
. $Support
Find-BuildPython -Explicit $Interpreter -RepoRoot $Root
''',encoding='utf-8')
    result=subprocess.run([SHELL,'-NoProfile','-ExecutionPolicy','Bypass','-File',str(wrapper),'-Support',str(ROOT/'tools/build_support.ps1'),'-Interpreter',sys.executable,'-Root',str(tmp_path)],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    assert Path(result.stdout.strip()).is_file()
    assert 'WindowsApps' not in result.stdout


def test_store_alias_is_rejected_without_running_it(tmp_path):
    alias=tmp_path/'Microsoft/WindowsApps/python.exe';alias.parent.mkdir(parents=True);alias.write_bytes(b'not a real interpreter')
    wrapper=tmp_path/'alias.ps1'
    wrapper.write_text('''param($Support,$Alias,$Root)
$ErrorActionPreference='Stop'
. $Support
Find-BuildPython -Explicit $Alias -RepoRoot $Root
''',encoding='utf-8')
    result=subprocess.run([SHELL,'-NoProfile','-ExecutionPolicy','Bypass','-File',str(wrapper),'-Support',str(ROOT/'tools/build_support.ps1'),'-Alias',str(alias),'-Root',str(tmp_path)],capture_output=True,text=True)
    assert result.returncode!=0
    assert 'execution alias is not an interpreter' in result.stderr


def test_source_build_rejects_wrong_xex_before_building(tmp_path):
    xex=tmp_path/'default.xex';xex.write_bytes(b'wrong title')
    result=subprocess.run([SHELL,'-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'tools/build_ch2k8.ps1'),'-Source',str(xex),'-ValidateOnly'],capture_output=True,text=True)
    assert result.returncode!=0 and 'Unsupported XEX' in result.stderr


def test_native_xex_extraction_is_readonly_and_preserves_existing_file(tmp_path):
    tool=ROOT/'out/native-tools/ch2k8_tools.exe'
    if not tool.is_file():pytest.skip('Build native tools first')
    from test_launcher_import import make_iso
    image=make_iso(tmp_path);before=hashlib.sha256(image.read_bytes()).digest()
    output=tmp_path/'generated input/default.xex'
    command=[str(tool),'extract-xex',str(image),str(output),'--expected-xex-sha256',hashlib.sha256(b'XEX2 fixture').hexdigest()]
    result=subprocess.run(command,capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    assert output.read_bytes()==b'XEX2 fixture'
    assert json.loads(result.stdout)['xex']
    assert subprocess.run(command,capture_output=True).returncode==0
    output.write_bytes(b'keep existing edits')
    assert subprocess.run(command,capture_output=True).returncode!=0
    assert output.read_bytes()==b'keep existing edits'
    assert hashlib.sha256(image.read_bytes()).digest()==before


def test_launcher_build_validation_rejects_wrong_xex_without_starting_build(tmp_path):
    xex=tmp_path/'wrong.xex';xex.write_bytes(b'wrong title')
    result=subprocess.run([SHELL,'-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'tools/launch_ch2k8.ps1'),'-BuildSource',str(xex),'-ValidateOnly'],capture_output=True,text=True)
    assert result.returncode!=0 and 'Unsupported XEX' in result.stderr


def test_native_import_handles_deep_derived_header_paths(tmp_path):
    tool=ROOT/'out/native-tools/ch2k8_tools.exe'
    if not tool.is_file():pytest.skip('Build native tools first')
    from test_loose_assets import make_disc
    source=tmp_path/'disc';make_disc(source)
    parent=tmp_path/('nested-installation-'+'a'*22)/('nested-installation-'+'b'*22)/('nested-installation-'+'c'*22)
    parent.mkdir(parents=True)
    output=parent/'game'
    result=subprocess.run([str(tool),'import',str(source),str(output),'--expected-xex-sha256',hashlib.sha256(b'XEX2 fixture').hexdigest()],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    assert (output/'assets.map').is_file()
    # The temporary import is deeper than its final destination; native metadata
    # writes must use Win32 extended paths without changing relative map entries.
    assert '_runtime/headers/' in (output/'assets.map').read_text()
    runtime=subprocess.run([str(tool),'validate-runtime',str(output)],capture_output=True,text=True)
    assert runtime.returncode==0,runtime.stderr
    assert not list(parent.glob('.ch2k8-import-*'))


def test_missing_input_creates_actionable_failure_report(tmp_path):
    log=tmp_path/'logs/build.log'
    result=subprocess.run([SHELL,'-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'tools/build_ch2k8.ps1'),'-Source',str(tmp_path/'missing.iso'),'-LogFile',str(log)],capture_output=True,text=True)
    assert result.returncode!=0
    report=json.loads((log.parent/'status.json').read_text(encoding='utf-8-sig'))
    assert report['state']=='failed' and report['stage']=='input'
    assert 'Input not found' in report['message']
    assert report['recovery'] and str(log) in result.stderr
    assert 'Input not found' in log.read_text()


@pytest.mark.parametrize('exit_code',[0,23])
def test_native_build_runner_drains_both_streams_and_reports_failure(tmp_path,exit_code):
    child=tmp_path/'compiler with spaces é.py'
    child.write_text('import sys\nprint("unicode path: é 日本語")\nfor i in range(2500):\n print("output-"+str(i))\n print("diagnostic-"+str(i),file=sys.stderr)\nprint("final compiler explanation",file=sys.stderr)\nsys.exit('+str(exit_code)+')\n',encoding='utf-8')
    wrapper=tmp_path/'worker.ps1'
    wrapper.write_text('''param($Support,$Interpreter,$Child,$Folder)
$ErrorActionPreference='Stop'
Import-Module (Join-Path $PSHOME 'Modules/Microsoft.PowerShell.Utility')
. $Support
$global:Ch2k8BuildContext=@{stage='start';source=$Child;log=(Join-Path $Folder 'build.log');status=(Join-Path $Folder 'status.json')}
Invoke-BuildCommand 'mock-compiler' $Interpreter @($Child) 'Retry with -Jobs 1 after checking memory.'
''',encoding='utf-8')
    result=subprocess.run([SHELL,'-NoProfile','-ExecutionPolicy','Bypass','-File',str(wrapper),'-Support',str(ROOT/'tools/build_support.ps1'),'-Interpreter',sys.executable,'-Child',str(child),'-Folder',str(tmp_path)],capture_output=True,text=True,timeout=45)
    log=(tmp_path/'build.log').read_text(encoding='utf-8')
    assert 'output-2499' in log and 'diagnostic-2499' in log
    assert 'unicode path: é 日本語' in log
    assert 'final compiler explanation' in log
    if exit_code:
        assert result.returncode!=0
        report=json.loads((tmp_path/'status.json').read_text(encoding='utf-8-sig'))
        assert report['stage']=='mock-compiler' and report['exit_code']==exit_code
        assert 'final compiler explanation' in report['message'] and '-Jobs 1' in report['recovery']
    else:
        assert result.returncode==0,result.stderr


def test_visual_studio_selection_uses_latest_complete_toolset(tmp_path):
    old=tmp_path/'VS 2022';new=tmp_path/'VS 2026';incomplete=tmp_path/'VS future without C++'
    for root in (old,new):
        headers=root/'VC/Tools/MSVC/14.99/include/vector';headers.parent.mkdir(parents=True);headers.touch()
        setup=root/'VC/Auxiliary/Build/vcvars64.bat';setup.parent.mkdir(parents=True);setup.touch()
    instances=tmp_path/'instances.json'
    instances.write_text(json.dumps([{'installationPath':str(old),'installationVersion':'17.9.0'},{'installationPath':str(incomplete),'installationVersion':'19.0.0'},{'installationPath':str(new),'installationVersion':'18.6.0'}]))
    wrapper=tmp_path/'select.ps1'
    wrapper.write_text('''param($Support,$Instances)
$ErrorActionPreference='Stop'
. $Support
Select-BuildVisualStudio (Get-Content -LiteralPath $Instances -Raw|ConvertFrom-Json)
''',encoding='utf-8')
    result=subprocess.run([SHELL,'-NoProfile','-ExecutionPolicy','Bypass','-File',str(wrapper),'-Support',str(ROOT/'tools/build_support.ps1'),'-Instances',str(instances)],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    assert Path(result.stdout.strip())==new
