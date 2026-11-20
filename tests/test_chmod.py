"""Exercise the shipped PowerShell backend and native preparer with synthetic Xbox data."""
import hashlib
import json
import shutil
import struct
import subprocess
import zipfile
from pathlib import Path

import pytest

from test_native_asset_tools import fixture_disc, IDENTITY, TOOL
from loose_assets import import_disc

ROOT = Path(__file__).resolve().parents[1]
PS = shutil.which('powershell.exe')
pytestmark = pytest.mark.skipif(not PS, reason='Windows PowerShell required')


def ps(tmp_path, body, *args, ok=True):
    script = tmp_path / 'exercise.ps1'
    script.write_text("$ErrorActionPreference='Stop'\n. $args[0]\n" + body, encoding='utf-8')
    result = subprocess.run([PS, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                             str(script), str(ROOT/'tools/chmod.ps1'), *map(str, args)],
                            capture_output=True, text=True, timeout=90)
    if ok:
        assert result.returncode == 0, result.stderr + result.stdout
    else:
        assert result.returncode != 0, result.stdout
    return result


def digest(data):
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def package(tmp_path):
    source = tmp_path/'disc'
    fixture_disc(source, 'texture')
    game = tmp_path/'game'
    import_disc(source, game, direct=True)
    entry = json.loads((game/'assets.json').read_text())['entries'][0]
    layout = json.loads((game/entry['folder']/'asset.json').read_text())
    record = layout['records'][0]
    target = entry['folder']+'/'+record['folder']+'/texture.dds'
    data = bytearray((game/target).read_bytes())
    data[128] ^= 0xff
    folder = tmp_path/'authored'
    (folder/'assets').mkdir(parents=True)
    (folder/'assets/art.dds').write_bytes(data)
    m = dict(schema_version=1, id='test.art', name='Synthetic artwork', author='Tests',
             version='1.0.0', requires=dict(xex_sha256=IDENTITY, recomp='ZMO-beta1', mod_api='1.0.0'),
             content=['assets'], capabilities=['dds.replace'], dependencies=[], incompatible=[],
             assets=[dict(bank_hash=entry['hash'], record_index=record['index'], record_id=record['id'],
                          record_type=record['type'], target=target,
                          source_sha256=digest((game/target).read_bytes()), file='assets/art.dds', sha256=digest(data))])
    (folder/'mod.json').write_text(json.dumps(m))
    return game, folder, m


def archive(tmp_path, folder):
    out = tmp_path/'art.chmod'
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        for f in folder.rglob('*'):
            if f.is_file():
                z.write(f, f.relative_to(folder).as_posix())
    return out


@pytest.mark.skipif(not TOOL.is_file(), reason='Native preparer required')
def test_texture_package_runtime_catalog_disable_and_rollback(tmp_path, package):
    game, folder, m = package
    original = {f.relative_to(game): digest(f.read_bytes()) for f in game.rglob('*') if f.is_file()}
    zip_path = archive(tmp_path, folder)
    result = ps(tmp_path, """
$null=Install-Chmod $args[1] $args[3]
$selection=@([pscustomobject]@{id='test.art';version='1.0.0'})
$plan=Resolve-Chmods $args[2] $args[3] $selection $args[6]
$tool=$args[5]
$cache=New-ChmodCache $args[2] $args[4] $plan {param($p) $null=& $tool prepare $p; if($LASTEXITCODE){throw 'Native preparation failed'}} -AssetTool $tool
$cached=New-ChmodCache $args[2] $args[4] $plan {throw 'Unchanged mod plan rebuilt its assets'} -AssetTool $tool
if($cached -ne $cache){throw 'Unchanged mod plan did not reuse its cache'}
$null=& $tool validate-runtime $cache; if($LASTEXITCODE){throw 'Runtime map rejected'}
$off=Resolve-Chmods $args[2] $args[3] @() $args[6]
$baseline=New-ChmodCache $args[2] $args[4] $off {throw 'Disable must not prepare a cache'}
if($baseline -ne $args[2]){throw 'Disable did not restore original root'}
$cache
""", zip_path, game, tmp_path/'mods', tmp_path/'cache', TOOL, IDENTITY)
    cache = Path(result.stdout.strip())
    assert (cache/m['assets'][0]['target']).read_bytes() == (folder/'assets/art.dds').read_bytes()
    assert len((cache/'native_dds.index').read_text().splitlines()) == 2
    assert json.loads((cache/'chmod-lock.json').read_text())['active'] == [{'id':'test.art', 'version':'1.0.0'}]
    assert original == {f.relative_to(game): digest(f.read_bytes()) for f in game.rglob('*') if f.is_file()}
    assert not list((tmp_path/'mods').glob('.install-*'))


@pytest.mark.parametrize('mutation', ['traversal','absolute','ads','record','revision','hash','mixed','unknown','float','self','undeclared'])
def test_reject_invalid_packages_or_identity(tmp_path, package, mutation):
    game, folder, m = package
    a = m['assets'][0]
    if mutation == 'traversal': a['file'] = '../art.dds'
    if mutation == 'absolute': a['file'] = 'C:/art.dds'
    if mutation == 'ads': a['file'] = 'assets/art.dds:code'
    if mutation == 'record': a['record_id'] ^= 1
    if mutation == 'revision': m['requires']['xex_sha256'] = '0'*64
    if mutation == 'hash': a['sha256'] = '0'*64
    if mutation == 'mixed': m['content'].append('rosters')
    if mutation == 'unknown': m['enabled'] = True
    if mutation == 'float': a['record_index'] = 0.5
    if mutation == 'self': m['dependencies'] = [dict(id=m['id'], version=m['version'])]
    if mutation == 'undeclared': (folder/'surprise.dll').write_bytes(b'code')
    (folder/'mod.json').write_text(json.dumps(m))
    failure=ps(tmp_path, """
$null=Install-Chmod $args[1] $args[3]
$null=Resolve-Chmods $args[2] $args[3] @([pscustomobject]@{id='test.art';version='1.0.0'}) $args[4]
""", folder, game, tmp_path/'mods', IDENTITY, ok=False)
    expected={'traversal':'Payload must', 'absolute':'Payload must', 'ads':'Payload must',
              'record':'identity differs', 'revision':'Wrong game revision', 'hash':'integrity differs',
              'mixed':'Content declaration differs', 'unknown':'Unsupported mod field', 'float':'Invalid resource integer',
              'self':'self dependency', 'undeclared':'Undeclared package file'}
    assert expected[mutation] in failure.stderr
    assert not list((tmp_path/'mods').glob('.install-*'))


@pytest.mark.parametrize('kind', ['escape','case-duplicate','symlink','bomb'])
def test_hostile_zip(tmp_path, kind):
    package = tmp_path/'bad.chmod'
    with zipfile.ZipFile(package, 'w', zipfile.ZIP_DEFLATED) as z:
        if kind == 'escape': z.writestr('../outside', b'bad')
        if kind == 'case-duplicate':
            z.writestr('mod.json', b'{}'); z.writestr('MOD.json', b'{}')
        if kind == 'symlink':
            item=zipfile.ZipInfo('link'); item.create_system=3; item.external_attr=0o120777 << 16
            z.writestr(item, b'../outside')
        if kind == 'bomb': z.writestr('assets/bomb.dds', bytes(2*1024*1024))
    ps(tmp_path, '$null=Install-Chmod $args[1] $args[2]', package, tmp_path/'mods', ok=False)
    assert not (tmp_path/'outside').exists()
    assert not list((tmp_path/'mods').iterdir())


def test_priority_versions_dependencies_and_failed_preparation(tmp_path, package):
    game, folder, m = package
    mods=tmp_path/'mods'; cache=tmp_path/'cache'
    ps(tmp_path, '$null=Install-Chmod $args[1] $args[2]', folder, mods)
    m['id']='test.second'; m['dependencies']=[dict(id='test.art', version='1.0.0')]
    (folder/'mod.json').write_text(json.dumps(m))
    ps(tmp_path, '$null=Install-Chmod $args[1] $args[2]', folder, mods)
    result=ps(tmp_path, """
$first=[pscustomobject]@{id='test.art';version='1.0.0'}
$second=[pscustomobject]@{id='test.second';version='1.0.0'}
$p=Resolve-Chmods $args[1] $args[2] @($first,$second) $args[4]
if($p.conflicts.Count -ne 1 -or $p.replacements[0].mod -ne 'test.second'){throw 'Wrong priority winner'}
$reverse=Resolve-Chmods $args[1] $args[2] @($second,$first) $args[4]
if($reverse.replacements[0].mod -ne 'test.art'){throw 'Wrong reversed priority'}
try { $null=New-ChmodCache $args[1] $args[3] $p {throw 'injected failure'}; throw 'Should have failed' } catch {if($_.Exception.Message -ne 'injected failure'){throw}}
$p | ConvertTo-Json -Depth 8
""", game, mods, cache, IDENTITY)
    assert json.loads(result.stdout)['conflicts']
    assert {entry.name for entry in cache.iterdir()} <= {'prepare.lock'}
    ps(tmp_path, "$null=Resolve-Chmods $args[1] $args[2] @([pscustomobject]@{id='test.second';version='1.0.0'}) $args[3]", game, mods, IDENTITY, ok=False)
    # Immutable update and retained old version.
    m['id']='test.art'; m['version']='1.1.0'; m['dependencies']=[]
    (folder/'mod.json').write_text(json.dumps(m))
    ps(tmp_path, '$null=Install-Chmod $args[1] $args[2]', folder, mods)
    assert (mods/'test.art/1.0.0/mod.json').is_file()
    assert (mods/'test.art/1.1.0/mod.json').is_file()
    ps(tmp_path, '$null=Install-Chmod $args[1] $args[2]', folder, mods, ok=False)


def test_folder_junction_rejected(tmp_path, package):
    _, folder, _ = package
    outside=tmp_path/'external'; outside.mkdir()
    script=tmp_path/'junction.ps1'
    script.write_text("$ErrorActionPreference='Stop'; $null=New-Item -ItemType Junction -Path $args[0] -Target $args[1]")
    result=subprocess.run([PS,'-NoProfile','-ExecutionPolicy','Bypass','-File',str(script),str(folder/'escape'),str(outside)],capture_output=True,text=True)
    if result.returncode and 'Access is denied' in result.stderr:
        pytest.skip('Sandbox denies junction creation; ZIP symlink rejection is covered separately')
    assert result.returncode == 0, result.stderr
    ps(tmp_path, '$null=Install-Chmod $args[1] $args[2]', folder, tmp_path/'mods', ok=False)


@pytest.mark.parametrize('kind',['duplicate','escaped-duplicate','trailing-comma','nested','source-component','source-dds','missing-version','cycle','incompatible'])
def test_strict_metadata_and_source_binding(tmp_path, package, kind):
    game, folder, m=package
    text=json.dumps(m)
    if kind=='duplicate': text=text.replace('"schema_version": 1', '"schema_version": 1, "schema_version": 1')
    if kind=='escaped-duplicate': text=text.replace('"schema_version": 1', '"schema_version": 1, "schema_versi\\u006fn": 1')
    if kind=='trailing-comma': text=text[:-1]+',}'
    if kind=='nested': text='['*33+'0'+']'*33
    if kind=='source-component':
        bank=game/json.loads((game/'assets.json').read_text())['entries'][0]['folder']
        layout=json.loads((bank/'asset.json').read_text()); f=bank/layout['blocks'][0]['components'][0]['path']
        data=bytearray(f.read_bytes());data[-1]^=1;f.write_bytes(data)
    if kind=='source-dds':
        f=game/m['assets'][0]['target'];data=bytearray(f.read_bytes());data[-1]^=1;f.write_bytes(data)
    if kind=='missing-version':
        m['dependencies']=[dict(id='uninstalled',version='9.0.0')];text=json.dumps(m)
    if kind=='incompatible': m['incompatible']=['test.art'];text=json.dumps(m)
    if kind=='cycle':
        m['dependencies']=[dict(id='test.second',version='1.0.0')];text=json.dumps(m)
        second=tmp_path/'second';shutil.copytree(folder,second)
        m2=dict(m,id='test.second',dependencies=[dict(id='test.art',version='1.0.0')])
        (second/'mod.json').write_text(json.dumps(m2))
        ps(tmp_path,'$null=Install-Chmod $args[1] $args[2]',second,tmp_path/'mods')
    (folder/'mod.json').write_text(text)
    failure=ps(tmp_path,"""
$null=Install-Chmod $args[1] $args[3]
$selection=@([pscustomobject]@{id='test.art';version='1.0.0'})
if($args[5] -eq 'cycle'){$selection += [pscustomobject]@{id='test.second';version='1.0.0'}}
$null=Resolve-Chmods $args[2] $args[3] $selection $args[4]
""",folder,game,tmp_path/'mods',IDENTITY,kind,ok=False)
    expected={'duplicate':'Duplicate JSON key', 'escaped-duplicate':'Duplicate JSON key','trailing-comma':'Trailing JSON comma','nested':'nesting limit',
              'source-component':'Source component changed','source-dds':'source template differs',
              'missing-version':'Missing dependency', 'cycle':'dependency cycle','incompatible':'Incompatible mods'}
    assert expected[kind] in failure.stderr


@pytest.mark.skipif(not TOOL.is_file(), reason='Native preparer required')
def test_shared_pixel_identity_cannot_silently_override_other_owner(tmp_path, package):
    game, folder, m=package
    # Two distinct Xbox bank hashes refer to identical source IFF bytes. They
    # become separate owner folders, but the GPU cannot distinguish their pixels.
    source=tmp_path/'shared-disc';fixture_disc(source,'texture')
    data=bytearray((source/'0A').read_bytes());struct.pack_into('>I',data,16,2)
    entry=list(struct.unpack_from('>4I',data,40));entry[0]=0x22223333
    payload=bytes(data[2048:2048+entry[3]])
    entry[1]=len(data)//2048
    data.extend(payload+bytes((-len(payload))%2048))
    struct.pack_into('>I',data,24,len(data)//2048)
    struct.pack_into('>4I',data,56,*entry);(source/'0A').write_bytes(data)
    shared=tmp_path/'shared-game';import_disc(source,shared,direct=True)
    failure=ps(tmp_path,"""
$null=Install-Chmod $args[1] $args[3]
$p=Resolve-Chmods $args[2] $args[3] @([pscustomobject]@{id='test.art';version='1.0.0'}) $args[6]
$tool=$args[5]
$null=New-ChmodCache $args[2] $args[4] $p {param($p) $output=& $tool prepare $p 2>&1; if($LASTEXITCODE){throw ($output -join ' ')}}
""",folder,shared,tmp_path/'mods',tmp_path/'cache',TOOL,IDENTITY,ok=False)
    assert 'Conflicting native DDS identities' in failure.stderr
    assert {entry.name for entry in (tmp_path/'cache').iterdir()} <= {'prepare.lock'}


def test_checked_in_example_installs_and_rejects_retail_binding(tmp_path):
    example=ROOT/'examples/synthetic-art.chmod'
    ps(tmp_path,'$null=Install-Chmod $args[1] $args[2]',example,tmp_path/'mods')
    m=json.loads((tmp_path/'mods/example.synthetic-art/1.0.0/mod.json').read_text())
    assert m['requires']['xex_sha256']==IDENTITY

def test_nested_collection_preserves_paths_and_resolves_children(tmp_path, package):
    game, folder, manifest = package
    collection = tmp_path / 'Presentation Overhaul V1.0'
    child = collection / 'Texture Mods' / 'Menus' / 'Scorebug Pack'
    shutil.copytree(folder, child)
    second = collection / 'Texture Mods' / 'Conference Courts' / 'SEC'
    shutil.copytree(folder, second)
    other = dict(manifest, id='test.courts')
    (second / 'mod.json').write_text(json.dumps(other))
    mods = tmp_path / 'mods'
    result = ps(tmp_path, """
$receipt=Install-Chmod $args[1] $args[2] -ModFolder
if($receipt.packages -ne 2){throw 'Expected both children'}
$found=@(Get-InstalledChmods $args[2])
if($found.Count -ne 2){throw 'Expected both installed children'}
$selection=@($found | ForEach-Object {[pscustomobject]@{id=$_.manifest.id;version=$_.manifest.version}})
$plan=Resolve-Chmods $args[3] $args[2] $selection -ExpectedXex $args[4]
if($plan.active.Count -ne 2){throw 'Nested mods did not resolve'}
if(-not ($plan.replacements[0].file -like '*Presentation Overhaul V1.0*')){throw 'Nested payload path was lost'}
Write-Output 'nested collection ok'
""", collection, mods, game, IDENTITY)
    assert 'nested collection ok' in result.stdout
    assert (mods / collection.name / 'Texture Mods' / 'Menus' / 'Scorebug Pack' / 'mod.json').is_file()
    rejected = tmp_path / 'Rejected Collection'
    shutil.copytree(collection, rejected)
    result = ps(tmp_path, 'Install-Chmod $args[1] $args[2] -ModFolder', rejected, mods, ok=False)
    assert 'Mod version already exists' in result.stderr
    assert not (mods / rejected.name).exists()
