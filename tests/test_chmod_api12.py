"""API 1.2 cases authored for the user's later execution. Never open the game.

Synthetic PE parsing does not LoadLibrary. Native uniform checks use synthetic
Xbox files; this suite is not an in-game acceptance claim.
"""
import copy
import json
import shutil
import struct
import zlib

import pytest

from test_chmod import ps, digest, package
from test_native_asset_tools import fixture_disc, IDENTITY
from test_chmod_contracts import native
from loose_assets import import_disc


def fake_dll():
    b=bytearray(512);b[:2]=b'MZ';struct.pack_into('<I',b,60,128)
    b[128:132]=b'PE\0\0';struct.pack_into('<H',b,132,0x8664)
    struct.pack_into('<H',b,150,0x2000);struct.pack_into('<H',b,152,0x20b)
    return b


def code_manifest(name='test.native'):
    data=fake_dll()
    return dict(schema_version=1,id=name,name='Synthetic native manifest',author='Tests',version='1.0.0',
                requires=dict(xex_sha256=IDENTITY,recomp='ZMO-beta1',mod_api='1.2.0'),
                content=['code'],capabilities=['hook.player.weight.read'],dependencies=[],incompatible=[],assets=[],
                extensions=[dict(file='code/synthetic.dll',sha256=digest(data),abi=1,hook='player.weight.read')])


def write_code(folder,manifest):
    (folder/'code').mkdir(parents=True);(folder/'code/synthetic.dll').write_bytes(fake_dll())
    (folder/'mod.json').write_text(json.dumps(manifest))


def test_native_opt_in_and_exclusive_hook(tmp_path,package):
    game,_,_=package;mods=tmp_path/'mods'
    for index in (1,2):
        folder=tmp_path/f'code-{index}';write_code(folder,code_manifest(f'test.native{index}'))
        ps(tmp_path,'$null=Install-Chmod $args[1] $args[2]',folder,mods)
    failed=ps(tmp_path,"""
$null=Resolve-Chmods $args[1] $args[2] @([pscustomobject]@{id='test.native1';version='1.0.0'}) $args[3]
""",game,mods,IDENTITY,ok=False)
    assert 'opt-in' in failed.stderr
    ps(tmp_path,"""
$p=Resolve-Chmods $args[1] $args[2] @([pscustomobject]@{id='test.native1';version='1.0.0'}) $args[3] -AllowCode $true
if($p.extensions.Count -ne 1 -or $p.extensions[0].hook -cne 'player.weight.read'){throw 'Unexpected native hook plan'}
""",game,mods,IDENTITY)
    failed=ps(tmp_path,"""
$null=Resolve-Chmods $args[1] $args[2] @([pscustomobject]@{id='test.native1';version='1.0.0'},[pscustomobject]@{id='test.native2';version='1.0.0'}) $args[3] -AllowCode $true
""",game,mods,IDENTITY,ok=False)
    assert 'registration conflict' in failed.stderr


@pytest.mark.parametrize('mutation',['wrong-machine','not-dll','unknown-hook','wrong-abi','undeclared-code','boolean-api'])
def test_native_manifest_rejections(tmp_path,mutation):
    folder=tmp_path/'source';m=code_manifest();write_code(folder,m)
    data=fake_dll()
    if mutation=='wrong-machine':struct.pack_into('<H',data,132,0x14c)
    if mutation=='not-dll':struct.pack_into('<H',data,150,0)
    if mutation=='unknown-hook':m['extensions'][0]['hook']='legacy.schedule.unknown'
    if mutation=='wrong-abi':m['extensions'][0]['abi']=99
    if mutation=='undeclared-code':m['content']=['assets']
    if mutation=='boolean-api':m['requires']['mod_api']=True
    (folder/'code/synthetic.dll').write_bytes(data);m['extensions'][0]['sha256']=digest(data)
    (folder/'mod.json').write_text(json.dumps(m))
    ps(tmp_path,'$null=Install-Chmod $args[1] $args[2]',folder,tmp_path/'mods',ok=False)


def test_boolean_opt_in_is_not_a_string(tmp_path):
    ps(tmp_path,"Assert-ChmodSettings ([pscustomobject]@{version=1;enabled=@();allow_native_code='false'})",ok=False)


@pytest.mark.parametrize('mutation',[None,'shared-stock-pixels','layout','header','component-size'])
def test_uniform_clone_native_contract(tmp_path,mutation):
    source=tmp_path/'disc';fixture_disc(source,'texture')
    game=tmp_path/'game';import_disc(source,game,direct=True)
    metadata=json.loads((game/'assets.json').read_text());entry=metadata['entries'][0]
    old_hash=entry['hash'];source_hash=zlib.crc32(b'SELUH000.IFF')&0xffffffff
    old_folder=game/entry['folder'];template=game/'assets/seluh000.iff';old_folder.rename(template)
    entry['hash']=source_hash;entry['folder']='assets/seluh000.iff'
    flags=metadata['loader_metadata']['toc_flags'].pop(str(old_hash))
    metadata['loader_metadata']['toc_flags'][str(source_hash)]=flags
    (game/'assets.json').write_text(json.dumps(metadata))
    source_meta=(template/'asset.json').read_bytes();layout=json.loads(source_meta)
    bank=tmp_path/'authored';shutil.copytree(template,bank)
    candidate=copy.deepcopy(layout)
    name='selux501.iff';candidate['identity']=dict(name=name,hash=zlib.crc32(name.upper().encode())&0xffffffff,
                                                 source_size=entry['size'],toc_flags=flags,template_hash=source_hash)
    component=bank/layout['blocks'][0]['components'][0]['path'];data=bytearray(component.read_bytes())
    if mutation!='shared-stock-pixels':data[0x1000]^=0x80
    if mutation=='component-size':data.extend(b'\0')
    component.write_bytes(data)
    if mutation=='layout':candidate['records'][0]['id']^=1
    if mutation=='header':
        head=bank/layout['pieces'][0]['path'];b=bytearray(head.read_bytes());b[0]^=1;head.write_bytes(b)
    (bank/'asset.json').write_text(json.dumps(candidate))
    result=native('validate-uniform',game,bank,source_hash,name,digest(source_meta))
    if mutation is None:
        assert result.returncode==0,result.stderr
        proof=json.loads(result.stdout)
        assert proof['artwork']==501 and proof['selection'] is True and proof['variant']==2
        assert proof['layout']['identity']==candidate['identity']
    else:assert result.returncode!=0
