"""API 1.1 regression cases, authored but NOT RUN at the user's request.

All payloads are synthetic; no game, real save, editor UI or desktop input is used.
"""
import json
import struct
import subprocess

import pytest

from test_native_asset_tools import TOOL
from test_chmod import ps, digest, package
from test_native_asset_tools import IDENTITY

pytestmark=pytest.mark.skipif(not TOOL.is_file(),reason='Build the native CHMOD tools')


def synthetic_roster():
    data=bytearray(8192)
    layout={}; cursor=0x100
    for name,field,bias,stride in [('players',8,17,316),('arenas',0x20,25,28),
                                  ('teams',0x28,49,704),('coaches',0x38,21,44),
                                  ('conferences',0xa8,1,2964),('uniforms',0x70,1,8)]:
        cursor=(cursor+63)&~63;layout[name]=cursor
        struct.pack_into('>Ii',data,field,1,cursor-(field+4)+bias);cursor+=stride
    team=layout['teams']; conference=layout['conferences']
    for field,target,bias in [(team+0x48,conference,1),(team+0x6c,layout['players'],17),
                              (conference+0x6e0,team,49)]:
        struct.pack_into('>i',data,field,target-field+bias)
    struct.pack_into('>H',data,team+0x188,1)
    struct.pack_into('>H',data,conference+0x870,1)
    header=bytearray(328);struct.pack_into('>II',header,0,1,1)
    header[8:20]='Roster'.encode('utf-16-be');header[264:275]=b'Roster.ROS\0'
    struct.pack_into('>I',header,316,0x54540818)
    return struct.pack('>I',len(data))+data, header, layout


def native(*args):
    return subprocess.run([str(TOOL),*map(str,args)],capture_output=True,text=True,timeout=30)


@pytest.mark.parametrize('mutation',[None,'length','title','profile','legacy-name','team-count','backlink'])
def test_native_roster_contract(tmp_path,mutation):
    data,head,layout=synthetic_roster();data=bytearray(data)
    if mutation=='length':data[3]^=1
    if mutation=='title':head[316]^=1
    if mutation=='profile':head[308]=1
    if mutation=='legacy-name':head[264:275]=b'Legacy.LEG\0'
    if mutation=='team-count':struct.pack_into('>H',data,4+layout['teams']+0x188,19)
    if mutation=='backlink':struct.pack_into('>i',data,4+layout['teams']+0x48,0)
    save=tmp_path/'Roster.ROS';save.write_bytes(data)
    header=tmp_path/'Roster.ROS.header';header.write_bytes(head)
    result=native('validate-roster',save,header)
    if mutation:assert result.returncode!=0
    else:
        assert result.returncode==0,result.stderr
        proof=json.loads(result.stdout)
        assert proof['players']==1 and proof['teams']==1 and len(proof['uniform_routes'])==1


def synthetic_cloth():
    data=bytearray(0x300);part=0x80;desc=0x140;decl=0x180;vertices=0x200;indices=0x240
    def word(off,value):struct.pack_into('>I',data,off,value)
    def pointer(off,target):struct.pack_into('>i',data,off,target-off+1)
    word(0x44,1);pointer(0x48,part)
    word(part+0x7c,1);word(part+0x84,1);pointer(part+0x88,desc)
    word(part+0x98,1);pointer(part+0x9c,decl)
    word(part+0xa4,16);word(part+0xa8,3);pointer(part+0xac,indices)
    word(desc+8,3);word(desc+12,1<<16);word(desc+28,12);word(desc+32,36);pointer(desc+36,vertices)
    data[decl+8:decl+12]=bytes([0x20,0,0,0]);word(decl+12,57)
    struct.pack_into('>9f',data,vertices,0,0,0,1,0,0,0,1,0)
    struct.pack_into('>3H',data,indices,0,1,2)
    return data


@pytest.mark.parametrize('mutation',['position','topology','declaration','resize','nonfinite'])
def test_source_compatible_cloth_contract(tmp_path,mutation):
    data=synthetic_cloth();changed=bytearray(data)
    if mutation=='position':struct.pack_into('>f',changed,0x200,0.25)
    if mutation=='topology':changed[0x241]^=1
    if mutation=='declaration':changed[0x18f]^=1
    if mutation=='resize':changed.extend(b'\0')
    if mutation=='nonfinite':struct.pack_into('>f',changed,0x200,float('nan'))
    source=tmp_path/'source.dat';source.write_bytes(data)
    target=tmp_path/'target.dat';target.write_bytes(changed)
    result=native('validate-cloth',source,target)
    assert (result.returncode==0)==(mutation=='position'),result.stderr


@pytest.mark.parametrize('display, filename', [
    ('Roster', 'Roster.ROS'),
    ('Custom Team', 'Custom Team.ROS'),
    ('CON', 'Roster.ROS'),
])
def test_roster_profile_isolation_and_persistent_reuse(tmp_path, display, filename):
    data,head,_=synthetic_roster()
    head[8:264] = display.encode('utf-16-be').ljust(256, b'\0')
    save=tmp_path/'Roster.ROS';save.write_bytes(data)
    header=tmp_path/'Roster.ROS.header';header.write_bytes(head)
    baseline=tmp_path/'baseline';profile=baseline/'B13EBABEBABEBABE/54540818'
    original=profile/'00000001/Roster.ROS/Roster.ROS';original.parent.mkdir(parents=True);original.write_bytes(b'user original')
    legacy=profile/'00000001/Legacy.LEG/Legacy.LEG';legacy.parent.mkdir(parents=True);legacy.write_bytes(b'user legacy')
    result=ps(tmp_path,"""
$r=[pscustomobject]@{mod='test.roster';version='1.0.0';file=$args[1];header=$args[2];sha256=$args[5];header_sha256=$args[6]}
$p=[pscustomobject]@{active=@([pscustomobject]@{id='test.roster';version='1.0.0'});replacements=@();roster=$r}
$first=New-ChmodRosterProfile $args[3] $args[4] $p
$name=$args[7]
$save=Join-Path $first "B13EBABEBABEBABE/54540818/00000001/$name/$name"
if((Get-ModHash $save) -cne $args[5]){throw 'Staged roster differs from its seed'}
[IO.File]::AppendAllText($save,'user edit')
$again=New-ChmodRosterProfile $args[3] $args[4] $p
if($first -ne $again){throw 'Profile selection was not stable'}
$p.roster=$null
if((New-ChmodRosterProfile $args[3] $args[4] $p) -ne $args[3]){throw 'Disable did not return baseline'}
$first
""",save,header,baseline,tmp_path/'profiles',digest(data),digest(head),filename)
    isolated=__import__('pathlib').Path(result.stdout.strip())
    assert original.read_bytes()==b'user original' and legacy.read_bytes()==b'user legacy'
    profile = isolated/'B13EBABEBABEBABE/54540818'
    assert (profile/'00000001'/filename/filename).read_bytes() == data + b'user edit'
    saved_header = (profile/'Headers/00000001'/(filename+'.header')).read_bytes()
    assert saved_header[264:306].split(b'\0', 1)[0] == filename.encode('ascii')
    assert not (isolated/'B13EBABEBABEBABE/54540818/00000001/Legacy.LEG').exists()
    assert (isolated/'baseline-backup/00000001/Roster.ROS/Roster.ROS').read_bytes()==b'user original'


def test_mixed_data_package_and_missing_linked_uniform_rejection(tmp_path,package):
    game,folder,manifest=package
    data,head,_=synthetic_roster();(folder/'rosters').mkdir()
    (folder/'rosters/Roster.ROS').write_bytes(data)
    (folder/'rosters/Roster.ROS.header').write_bytes(head)
    manifest['requires']['mod_api']='1.1.0'
    manifest['content']=['assets','rosters'];manifest['capabilities']=['dds.replace','roster.expose']
    manifest['roster']=dict(file='rosters/Roster.ROS',sha256=digest(data),
                            header='rosters/Roster.ROS.header',header_sha256=digest(head))
    (folder/'mod.json').write_text(json.dumps(manifest))
    mods=tmp_path/'mods'
    ps(tmp_path,'$null=Install-Chmod $args[1] $args[2]',folder,mods)
    failure=ps(tmp_path,"""
$null=Resolve-Chmods $args[1] $args[2] @([pscustomobject]@{id='test.art';version='1.0.0'}) $args[3]
""",game,mods,IDENTITY,ok=False)
    # This fixture deliberately has no registered uh000/seluh000 bank. A native
    # roster is not permitted to activate without its linked asset identities.
    assert 'unregistered uniform bank' in failure.stderr


def test_semver_comparison_does_not_truncate_large_components(tmp_path):
    ps(tmp_path,"""
if((Compare-ModVersion '1.10.0' '1.2.0') -ne 1){throw 'Lexical version ordering'}
if((Compare-ModVersion '1.0.0' '1.0.0') -ne 0){throw 'Version equality'}
if((Compare-ModVersion '999999999999999999999.0.0' '2.0.0') -ne 1){throw 'Version component truncation'}
""")
