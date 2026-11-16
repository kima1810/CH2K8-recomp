"""Runtime updater regressions, authored but NOT RUN. Synthetic files only.
No network, game, DLL loading, downloaded scripts or real saves are executed.
"""
import hashlib,json,shutil,subprocess,zipfile
from pathlib import Path
import pytest
from test_launcher import fake_pe
ROOT=Path(__file__).resolve().parents[1]
PS=shutil.which('powershell.exe')
pytestmark=pytest.mark.skipif(not PS,reason='Windows PowerShell required')
XEX='71e8983d1cc009e485696aad19b5fa4b4661761870e2c8972717b932c1e4be36'


def run(tmp_path,body,*args,ok=True):
    script=tmp_path/'updater-exercise.ps1'
    script.write_text("$ErrorActionPreference='Stop'\n. $args[0]\n. $args[1]\n"+body)
    result=subprocess.run([PS,'-NoProfile','-ExecutionPolicy','Bypass','-File',str(script),str(ROOT/'tools/chmod.ps1'),str(ROOT/'tools/runtime_update.ps1'),*map(str,args)],capture_output=True,text=True,timeout=60)
    assert (result.returncode==0)==ok,result.stdout+result.stderr
    return result


def digest(data):return hashlib.sha256(data).hexdigest()


def package(folder,api='1.3.0',caps=None):
    folder.mkdir(parents=True)
    binaries=['ch2k8.exe','rexruntime.dll','rexgpu-xenos.dll','ch2k8_tools.exe','msvcp140.dll','vcruntime140.dll','vcruntime140_1.dll','msvcp140_atomic_wait.dll']
    for name in binaries:(folder/name).write_bytes(fake_pe())
    for name in ['launch_ch2k8','chmod','chmod_ui','runtime_update','update_runtime','pe_imports','beta_diagnostics']:
        path=folder/'tools'/(name+'.ps1');path.parent.mkdir(exist_ok=True);path.write_text("throw 'Downloaded scripts MUST NOT execute during update verification'\n")
    docs=folder/'docs/formats';docs.mkdir(parents=True)
    (docs/'chmod.schema.json').write_text('{}');(docs/'hook_registry.json').write_text('{}')
    (folder/'gamecontrollerdb.txt').write_text('synthetic controller data')
    (folder/'runtime-update.json').write_text(json.dumps(dict(format=1,bootstrap_protocol=1,platform='windows-x64',package_type='runtime',xex_sha256=XEX,mod_api=api)))
    receipt=dict(mod_api=api,xex_sha256=XEX,exe_sha256=digest((folder/'ch2k8.exe').read_bytes()),hooks=['player.weight.read'],extension_abis=[1,2],capabilities=caps or ['hook.player.weight.read'])
    (folder/'chmod-runtime.json').write_text(json.dumps(receipt))
    (folder/'beta-version.json').write_text(json.dumps(dict(platform='windows-x64',game_data_included=False,build_files={name:digest((folder/name).read_bytes()) for name in binaries[:4]})))
    inventory(folder)
    return receipt


def inventory(folder):
    lines=[digest(p.read_bytes())+'  '+p.relative_to(folder).as_posix() for p in sorted(folder.rglob('*')) if p.is_file() and p.name!='SHA256SUMS.txt']
    (folder/'SHA256SUMS.txt').write_text('\n'.join(lines)+'\n')


def archive(folder,output):
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
        for p in folder.rglob('*'):
            if p.is_file():z.write(p,'Build-1/'+p.relative_to(folder).as_posix())


def asset(name,updated):
    return dict(id=1,name=name,updated_at=updated,size=100,state='uploaded',digest='sha256:'+'a'*64,browser_download_url='https://github.com/kima1810/CH2K8-recomp/releases/download/tag/'+name)


def test_release_selection_includes_beta_and_newest_windows_asset(tmp_path):
    releases=[dict(id=1,draft=False,published_at='2026-11-06T00:00:00Z',prerelease=True,assets=[asset('CH2K8-ZMO-beta1-Windows-x64-old.zip','2026-11-06T00:00:00Z'),asset('CH2K8-ZMO-beta1-Windows-x64-new.zip','2026-11-07T00:00:00Z'),asset('CH2K8-ZMO-beta1-Source-new.zip','2026-11-08T00:00:00Z')]),dict(id=2,draft=True,published_at='2026-11-09T00:00:00Z',assets=[])]
    path=tmp_path/'releases.json';path.write_text(json.dumps(releases))
    result=run(tmp_path,"$r=Select-Ch2k8Release (Read-ModJson $args[2]);$r.asset.name",path)
    assert 'Windows-x64-new.zip' in result.stdout


@pytest.mark.parametrize('mutation',['checksum','unlisted','old-api','lost-capability','missing-protocol','protected-path','wrong-machine','unbundled-dependency'])
def test_payload_rejections_do_not_execute_payload(tmp_path,mutation):
    payload=tmp_path/'payload';receipt=package(payload)
    current=tmp_path/'current';current.mkdir();(current/'chmod-runtime.json').write_text(json.dumps(receipt))
    if mutation=='checksum':(payload/'gamecontrollerdb.txt').write_text('changed')
    elif mutation=='unlisted':(payload/'docs/unlisted.md').write_text('extra')
    elif mutation=='old-api':
        for name in ['runtime-update.json','chmod-runtime.json']:
            p=payload/name;data=json.loads(p.read_text());data['mod_api']='1.2.0';p.write_text(json.dumps(data))
        inventory(payload)
    elif mutation=='lost-capability':
        p=current/'chmod-runtime.json';data=json.loads(p.read_text());data['capabilities'].append('hook.future.required');p.write_text(json.dumps(data))
    elif mutation=='missing-protocol':(payload/'runtime-update.json').unlink();inventory(payload)
    elif mutation=='protected-path':
        p=payload/'port/userdata/Roster.ROS';p.parent.mkdir(parents=True);p.write_bytes(b'not a save');inventory(payload)
    elif mutation in ('wrong-machine','unbundled-dependency'):
        data=bytearray(fake_pe('missing-dependency.dll') if mutation=='unbundled-dependency' else fake_pe())
        if mutation=='wrong-machine':data[0x84:0x86]=b'\x4c\x01'
        (payload/'rexruntime.dll').write_bytes(data)
        p=payload/'beta-version.json';m=json.loads(p.read_text());m['build_files']['rexruntime.dll']=digest(data);p.write_text(json.dumps(m));inventory(payload)
    run(tmp_path,'$null=Assert-Ch2k8RuntimeRelease $args[2] $args[3]',payload,current,ok=False)


@pytest.mark.parametrize('badname',['Build-1/../escape.txt','Build-1/mods/evil/mod.json','Build-1/port/userdata/settings.json','Elsewhere/file.txt','Build-1/tools/CON.ps1'])
def test_archive_paths_reject(tmp_path,badname):
    payload=tmp_path/'source';package(payload);z=tmp_path/'bad.zip';archive(payload,z)
    with zipfile.ZipFile(z,'a') as out:out.writestr(badname,b'bad')
    run(tmp_path,'Expand-Ch2k8RuntimeRelease $args[2] $args[3]',z,tmp_path/'stage',ok=False)
    assert not (tmp_path/'escape.txt').exists()


def test_symlink_and_case_collision_reject(tmp_path):
    payload=tmp_path/'source';package(payload)
    for mode in ['link','case']:
        z=tmp_path/(mode+'.zip');archive(payload,z)
        with zipfile.ZipFile(z,'a') as out:
            entry=zipfile.ZipInfo('Build-1/tools/link.ps1' if mode=='link' else 'Build-1/CH2K8.EXE')
            if mode=='link':entry.create_system=3;entry.external_attr=0o120777<<16
            out.writestr(entry,b'target')
        run(tmp_path,'Expand-Ch2k8RuntimeRelease $args[2] $args[3]',z,tmp_path/mode,ok=False)


def test_side_by_side_install_and_rollback_preserve_user_files(tmp_path):
    payload=tmp_path/'source';receipt=package(payload);z=tmp_path/'release.zip';archive(payload,z)
    root=tmp_path/'installation with spaces';root.mkdir()
    sentinels={root/'mods/user-mod/file.txt':b'user mod',root/'game/default.xex':b'private game',root/'port/userdata/B13EBABEBABEBABE/54540818/00000001/My.ROS/My.ROS':b'private save',root/'port/userdata/launcher.json':b'private settings',root/'ch2k8.exe':b'original runtime'}
    for p,data in sentinels.items():p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
    (root/'chmod-runtime.json').write_text(json.dumps(receipt))
    sha=digest(z.read_bytes());candidate=tmp_path/'candidate.json'
    candidate.write_text(json.dumps(dict(sha256=sha,asset=dict(name='CH2K8-Test-Windows-x64-new.zip',size=z.stat().st_size,browser_download_url='unused'),release=dict(tag_name='synthetic'))))
    run(tmp_path,"""
+$script:fixtureArchive=$args[3];$script:fixtureCandidate=$args[4]
+function Get-Process {param($Name)} # No real process interaction.
+function Get-Ch2k8LatestRelease {param($Job) Read-ModJson $script:fixtureCandidate}
+function Receive-Ch2k8UpdateFile {param($Url,$Output,$Limit,$Seconds) [IO.File]::Copy($script:fixtureArchive,$Output)}
+$root=$args[2];$state=Get-Ch2k8UpdateState $root;$job=Get-ModPath $state ('jobs/'+[guid]::NewGuid().ToString('N'));$null=[IO.Directory]::CreateDirectory($job)
+$null=Install-Ch2k8LatestRuntime $root $root $job
+$active=Get-Ch2k8ActiveRuntime $root
+if($active -ieq $root){throw 'Runtime was not selected'}
+$null=Install-Ch2k8LatestRuntime $root $active $job -Rollback
+if((Get-Ch2k8ActiveRuntime $root) -ine $root){throw 'Rollback did not select original runtime'}
+""".replace('\n+','\n'),root,z,candidate)
    assert all(p.read_bytes()==data for p,data in sentinels.items())
    assert (root/'port/userdata/runtime-updates/releases'/sha/'ch2k8.exe').is_file()
