"""ABI 2 package/metadata tests; authored but not executed by the agent."""
import json
from pathlib import Path
import pytest
from test_chmod import ps,digest,package
from test_chmod_api12 import fake_dll
ROOT=Path(__file__).resolve().parents[1]

def source(tmp_path):
    folder=tmp_path/'mod';(folder/'code').mkdir(parents=True)
    m=json.loads((ROOT/'sdk/examples/minimal/observe.json').read_text())
    data=fake_dll();(folder/'code/chmod_observe.dll').write_bytes(data)
    m['extensions'][0]['sha256']=digest(data)
    return folder,m

@pytest.mark.parametrize('mutation',[None,'old-api','unknown-capability','missing-claim-cap','abi-string','duplicate-cap'])
def test_sdk_package_contract(tmp_path,mutation):
    folder,m=source(tmp_path)
    e=m['extensions'][0]
    if mutation=='old-api':m['requires']['mod_api']='1.2.0'
    if mutation=='unknown-capability':e['capabilities'].append('simulation.unknown')
    if mutation=='missing-claim-cap':e['replacements']=['player.weight.write']
    if mutation=='abi-string':e['abi']='2'
    if mutation=='duplicate-cap':e['capabilities'].append(e['capabilities'][0])
    (folder/'mod.json').write_text(json.dumps(m))
    ps(tmp_path,'$null=Read-Chmod $args[1]',folder,ok=mutation is None)


def test_dispatch_symbol_coverage_source():
    pch=(ROOT/'port/generated/default/ch2k8_pch.h').read_text()
    adapters=(ROOT/'port/src/mod_extensions.cpp').read_text()
    for name in ('84752968','848425D8'):
        assert 'REX_HOOK_RAW(sub_'+name+')' in adapters
        assert '__imp__sub_'+name in adapters
    assert 'alias("__imp__" #name)' in pch
    # Full linker-map/direct-call/native-dispatch acceptance remains user-run.


@pytest.mark.parametrize('exclusive',[False,True])
def test_native_dependency_order_and_replacement_claims(tmp_path,package,exclusive):
    from test_native_asset_tools import IDENTITY
    game,_,_=package;mods=tmp_path/'mods'
    for name in ('a','b'):
        folder=tmp_path/name;folder.mkdir()
        root,m=source(folder);m['id']='test.'+name;m['requires']['xex_sha256']=IDENTITY
        if name=='a':m['dependencies']=[dict(id='test.b',version='1.0.0')]
        if exclusive:m['extensions'][0]['replacements']=['player.weight.read']
        (root/'mod.json').write_text(json.dumps(m))
        ps(tmp_path,'$null=Install-Chmod $args[1] $args[2]',root,mods)
    result=ps(tmp_path,"""
$selection=@([pscustomobject]@{id='test.a';version='1.0.0'},[pscustomobject]@{id='test.b';version='1.0.0'})
$p=Resolve-Chmods $args[1] $args[2] $selection $args[3] -AllowCode $true
if(($p.extensions.id -join ',') -cne 'test.b,test.a'){throw 'Native dependency order differs'}
""",game,mods,IDENTITY,ok=not exclusive)
    if exclusive:assert 'replacement conflict' in result.stderr
