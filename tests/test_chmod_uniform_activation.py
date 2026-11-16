"""Automatic Xbox alternate activation cases. Authored, NOT RUN by agent.
No game process or user saves are involved.
"""
import json
import struct

import pytest
from test_chmod_contracts import synthetic_roster, native


def inputs(tmp_path, name='Roster.ROS'):
    save, header, layout = synthetic_roster()
    header[264:306] = bytes(42)
    header[264:264+len(name)] = name.encode('ascii')
    payload = tmp_path / name
    head = tmp_path / (name+'.header')
    payload.write_bytes(save)
    head.write_bytes(header)
    request = tmp_path / 'request.json'
    request.write_text(json.dumps([dict(artwork=0, variant=2)]))
    output = tmp_path / 'output' / name
    return payload, head, request, output, layout


@pytest.mark.parametrize('name', ['Roster.ROS', 'Custom Team.ROS'])
def test_append_alternate_and_preserve_native_header(tmp_path, name):
    payload, head, request, output, layout = inputs(tmp_path, name)
    original = payload.read_bytes()
    header = head.read_bytes()
    result = native('activate-roster-uniforms', payload, head, request, output)
    assert result.returncode == 0, result.stderr
    proof = json.loads(result.stdout)
    assert proof['changes'] == [dict(owner=0, artwork=0, variant=2)]
    changed = output.read_bytes()
    assert payload.read_bytes() == original and head.read_bytes() == header
    assert struct.unpack_from('>I', changed)[0] == len(changed)-4
    assert struct.unpack_from('>I', changed, 4+0x70)[0] == 2
    at = 0x74 + struct.unpack_from('>i', changed, 4+0x74)[0]-1
    assert struct.unpack_from('>II', changed, 4+at+8) == (2<<8, 0)
    # All original payload bytes except wrapper/table descriptor remain exact.
    assert changed[4:4+0x70] == original[4:4+0x70]
    assert changed[4+0x78:len(original)] == original[4+0x78:]
    second = tmp_path / 'second' / name
    again = native('activate-roster-uniforms', output, head, request, second)
    assert again.returncode == 0, again.stderr
    assert json.loads(again.stdout)['changes'] == []
    assert second.read_bytes() == changed


@pytest.mark.parametrize('mutation', ['unmapped', 'conflict', 'header', 'dormant', 'home'])
def test_unsafe_activation_rejects_without_touching_input(tmp_path, mutation):
    payload, head, request, output, layout = inputs(tmp_path)
    data = bytearray(payload.read_bytes())
    if mutation == 'unmapped':
        request.write_text(json.dumps([dict(artwork=999, variant=2)]))
    if mutation == 'conflict':
        # Existing alternate points elsewhere. Add a Home route for art zero.
        start = layout['uniforms']
        struct.pack_into('>II', data, 4+start, (1<<12)|(2<<8), 0)
        target = len(data)-4
        data.extend(struct.pack('>II', 0, 0))
        # Build a contiguous Home+alternate table at EOF.
        target = len(data)-4
        data.extend(struct.pack('>IIII', 0, 0, (1<<12)|(2<<8), 0))
        struct.pack_into('>Ii', data, 4+0x70, 2, target-0x74+1)
        struct.pack_into('>I', data, 0, len(data)-4)
    if mutation == 'home':
        struct.pack_into('>I', data, 4+layout['uniforms'], 1<<8)
    if mutation == 'dormant':
        data.extend(b'XRUFv001')
        struct.pack_into('>I', data, 0, len(data)-4)
    payload.write_bytes(data)
    if mutation == 'header':
        bad = bytearray(head.read_bytes());bad[264] = ord('X');head.write_bytes(bad)
    before = payload.read_bytes()
    result = native('activate-roster-uniforms', payload, head, request, output)
    assert result.returncode != 0
    assert payload.read_bytes() == before and not output.exists()


def test_unlock_existing_without_any_mod_folder(tmp_path):
    payload, head, request, output, layout = inputs(tmp_path)
    data = bytearray(payload.read_bytes())
    struct.pack_into('>I', data, 4+layout['uniforms'], 73)
    payload.write_bytes(data)
    request.write_text(json.dumps(dict(unlock_existing=True, alternates=[])))
    result = native('activate-roster-uniforms', payload, head, request, output)
    assert result.returncode == 0, result.stderr
    changed = output.read_bytes()
    at = 0x74 + struct.unpack_from('>i', changed, 4+0x74)[0]-1
    assert struct.unpack_from('>I', changed, 4+at)[0] & 127 == 0
    assert struct.unpack_from('>I', changed, 4+0x70)[0] == 1
    assert payload.read_bytes() == data


def test_unused_vanilla_candidate_is_optional(tmp_path):
    payload, head, request, output, layout = inputs(tmp_path)
    request.write_text(json.dumps(dict(unlock_existing=True, alternates=[dict(artwork=999,variant=2,required=False)])))
    result = native('activate-roster-uniforms', payload, head, request, output)
    assert result.returncode == 0, result.stderr
    assert output.read_bytes() == payload.read_bytes()


def dummy_hdd(tmp_path):
    root = tmp_path/'hdd'
    original = {}
    for xuid, name in [('B13EBABEBABEBABE','Roster.ROS'),('0000000000000001','Custom Team.ROS')]:
        source = tmp_path/xuid
        source.mkdir()
        payload, header, _, _, _ = inputs(source,name)
        target = root/xuid/'54540818'/'00000001'/name/name
        target.parent.mkdir(parents=True)
        target.write_bytes(payload.read_bytes())
        h = root/xuid/'54540818'/'Headers'/'00000001'/(name+'.header')
        h.parent.mkdir(parents=True,exist_ok=True)
        h.write_bytes(header.read_bytes())
        original[target] = target.read_bytes()
    return root, original


def test_every_roster_and_journal_rollback(tmp_path):
    from test_chmod import ps
    root, original = dummy_hdd(tmp_path)
    state = tmp_path/'state'
    profiles = tmp_path/'profiles'
    ps(tmp_path,"$p=[pscustomobject]@{uniforms=@([pscustomobject]@{selection=$false;variant=2;artwork=0})}; Sync-ChmodRosterActivation $args[1] $args[2] $args[3] @($args[1]) $p",root,profiles,state)
    assert all(path.read_bytes()!=before for path,before in original.items())
    journal = json.loads((state/'active.json').read_text(encoding='utf-8-sig'))
    assert len(journal['entries']) == 2
    ps(tmp_path,'Restore-ChmodRosterActivation $args[1] $args[2] $args[3]',root,profiles,state)
    assert all(path.read_bytes()==before for path,before in original.items())
    assert not (state/'active.json').exists()


def test_modified_save_blocks_rollback_without_partial_restore(tmp_path):
    from test_chmod import ps
    root, original = dummy_hdd(tmp_path)
    state = tmp_path/'state'
    profiles = tmp_path/'profiles'
    ps(tmp_path,"$p=[pscustomobject]@{uniforms=@([pscustomobject]@{selection=$false;variant=2;artwork=0})}; Sync-ChmodRosterActivation $args[1] $args[2] $args[3] @($args[1]) $p",root,profiles,state)
    target = next(iter(original))
    changed = bytearray(target.read_bytes());changed[-1] ^= 1;target.write_bytes(changed)
    before = {path:path.read_bytes() for path in original}
    ps(tmp_path,'Restore-ChmodRosterActivation $args[1] $args[2] $args[3]',root,profiles,state,ok=False)
    assert all(path.read_bytes()==data for path,data in before.items())
    assert (state/'active.json').exists()
