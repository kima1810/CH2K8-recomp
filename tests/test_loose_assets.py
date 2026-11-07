"""Lossless importer primitives; no copyrighted fixture data."""
import struct
import sys
import subprocess
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from loose_assets import decode, encode_literals, contained, explode, write_map, import_disc, prepare, iff_layout, validate_dds
from xbox_texture import export_dds, apply_dds, tiled_offset


def texture():
    data = bytearray(0x3000)
    struct.pack_into('>iI', data, 0x6C, 0x1000-0x6C+1, 0x2000)
    struct.pack_into('>6I', data, 0x94, 0x80400002, 18|64, 31|(31<<13), 0, 0, 1<<9)
    data[0x1000:] = bytes(range(256))*32
    return bytes(data)


def test_dds_round_trip_and_edit():
    original = texture()
    dds = export_dds(original)
    assert apply_dds(original, dds) == original
    edit = bytearray(dds)
    edit[128:136] = b'\x12'*8
    changed = apply_dds(original, edit)
    assert changed[:0x1000] == original[:0x1000]
    assert export_dds(changed) == bytes(edit)


def test_reject_resize_and_truncation():
    original = texture()
    dds = bytearray(export_dds(original))
    struct.pack_into('<I', dds, 16, 64)
    with pytest.raises(ValueError, match='dimensions'):
        apply_dds(original, dds)
    with pytest.raises(ValueError, match='length'):
        apply_dds(original, export_dds(original)[:-1])


def test_tiling_has_no_aliases():
    for bpp in (3,4):
        offsets = [tiled_offset(x,y,64,bpp) for y in range(64) for x in range(64)]
        assert len(set(offsets)) == 4096
        assert min(offsets) == 0
        assert max(offsets)+(1<<bpp) == 4096*(1<<bpp)


def test_compression_and_opaque_preservation(tmp_path):
    data=bytes(range(256))*17
    assert decode(encode_literals(data,None),len(data)) == data
    layout=explode(data,tmp_path)
    assert b''.join((tmp_path/p['path']).read_bytes() for p in layout['pieces']) == data
    with pytest.raises(ValueError):
        decode(encode_literals(data,None)[:-2],len(data))


def test_block_encoder_preserves_codec_and_opaque_wrapper_fields():
    import zlib
    data=bytes(range(64));h7a=bytearray(encode_literals(data,None))
    struct.pack_into('>II',h7a,12,0x12345678,9)
    result=encode_literals(data[::-1],h7a)
    assert result[12:20]==h7a[12:20]
    assert decode(result,len(data))==data[::-1]
    assert encode_literals(data[::-1],data)==data[::-1]
    body=zlib.compress(data)
    original=struct.pack('>4sIII',b'ZLIB',len(data),16+len(body),0x87654321)+body
    result=encode_literals(data[::-1],original)
    assert result[:4]==b'ZLIB' and result[12:16]==original[12:16]
    assert decode(result,len(data))==data[::-1]


def test_map_rejects_missing_ranges_and_escape(tmp_path):
    (tmp_path/'a').write_bytes(b'abcd')
    valid=dict(parts=[dict(name='0A',offset=0,size=4)],segments=[dict(path='a',offset=0,size=4)])
    write_map(tmp_path,valid)
    assert (tmp_path/'assets.map').read_text().startswith('CH2K8_LOOSE_V1\n')
    valid['segments'][0]['offset']=1
    with pytest.raises(ValueError,match='coverage'):
        write_map(tmp_path,valid)
    with pytest.raises(ValueError,match='escapes'):
        contained(tmp_path,'../outside')


def make_disc(root):
    root.mkdir()
    (root/'default.xex').write_bytes(b'XEX2 fixture')
    header=bytearray(128)
    struct.pack_into('>8I',header,0,0xFF3BEF94,128,192,0,1,0,2,64-28+1)
    struct.pack_into('>8I',header,32,0,0xBB05A9C1,0,64,0,128,64,0)
    struct.pack_into('>2I',header,64,72-64+1,88-68+1)
    struct.pack_into('>4I',header,72,0x12345678,0xE26C9B5D,1,0)
    struct.pack_into('>4I',header,88,0x87654321,0xC61649B2,1,32)
    iff=bytes(header)+bytes(range(64))+b'opaque trailer'
    archive=bytearray(4096)
    struct.pack_into('>6I',archive,0,0xAA00B3BF,2048,1,0,1,0)
    struct.pack_into('>II8s',archive,24,2,0,'0A'.encode('utf-16-be').ljust(8,b'\0'))
    struct.pack_into('>4I',archive,40,0x11112222,1,0,len(iff))
    archive[2048:2048+len(iff)]=iff
    (root/'0A').write_bytes(archive)
    return bytes(archive),iff


def scatter_read(root,offset,size):
    result=bytearray()
    for line in (root/'assets.map').read_text().splitlines()[1:]:
        kind,start,length,path=line.split('\t');start,length=int(start),int(length)
        if kind!='S' or offset>=start+length or offset+size<=start:continue
        value=(root/path).read_bytes()
        left=max(start,offset);right=min(start+length,offset+size)
        result.extend(value[left-start:right-start])
    return bytes(result)


def test_folder_import_round_trip_and_scne_rost_edits(tmp_path):
    source=tmp_path/'source';original,iff=make_disc(source)
    root=tmp_path/'installed';manifest=import_disc(source,root,False)
    assert not (root/'0A').exists()
    assert scatter_read(root,0,len(original))==original
    folder=root/manifest['entries'][0]['folder']
    layout=__import__('json').loads((folder/'asset.json').read_text())
    assert {r['folder'].split('.')[-1] for r in layout['records']}=={'scne','rost'}
    roster=folder/layout['blocks'][0]['components'][1]['path']
    edited=bytearray(roster.read_bytes());edited[7]^=0xff;roster.write_bytes(edited)
    prepare(root)
    toc=scatter_read(root,40,16);_,units,_,size=struct.unpack('>4I',toc)
    rebuilt=scatter_read(root,units*2048,size);new_layout=iff_layout(rebuilt);block=new_layout['blocks'][0]
    body=decode(rebuilt[block['start']:block['start']+block['size']],block['logical'])
    expected=bytearray(range(64));expected[39]^=0xff
    assert body==expected
    assert rebuilt.endswith(b'opaque trailer')
    map_before=(root/'assets.map').read_bytes()
    roster.write_bytes(edited+b'extra')
    with pytest.raises(ValueError,match='resizing'):
        prepare(root)
    assert (root/'assets.map').read_bytes()==map_before
    roster.write_bytes(bytes(range(32,64)))
    prepare(root)
    assert scatter_read(root,0,len(original))==original


def test_native_dds_upscale_and_mip_validation():
    original=texture();dds=bytearray(export_dds(original));info=__import__('xbox_texture').describe(original)
    struct.pack_into('<II',dds,12,64,64)
    dds=dds[:128]+bytearray(64*64//2)
    assert validate_dds(dds,info)==(64,64,1)
    struct.pack_into('<I',dds,28,7)
    with pytest.raises(ValueError,match='payload'):
        validate_dds(dds,info)


def test_added_uniform_bank_rebuilds_virtual_sorted_toc_without_archive_chunks(tmp_path):
    import json,shutil,zlib
    source=tmp_path/'disc';archive,iff=make_disc(source);archive=bytearray(archive)
    original_hash=zlib.crc32(b'UH000.IFF')&0xffffffff;row=struct.pack('>4I',original_hash,1,0,len(iff))
    struct.pack_into('>I',archive,8,2)
    struct.pack_into('>II8s',archive,40,1,0,'0B'.encode('utf-16-be').ljust(8,b'\0'))
    archive[56:72]=row;(source/'0A').write_bytes(archive);(source/'0B').write_bytes(bytes(2048))
    root=tmp_path/'game';manifest=import_disc(source,root,False);entry=manifest['entries'][0]
    shutil.copytree(root/entry['folder'],root/'assets/ux900.iff')
    registry=dict(version=1,platform='xbox360',edits=[],banks=[dict(name='ux900.iff',folder='assets/ux900.iff',template=original_hash)])
    (root/'asset_edits.json').write_text(json.dumps(registry));prepare(root)
    header=scatter_read(root,0,128);assert struct.unpack_from('>I',header,16)[0]==2
    hashes=[];resources={}
    for i in range(2):
        identity,sector,unused,size=struct.unpack_from('>4I',header,56+i*16);hashes.append(identity);resources[identity]=scatter_read(root,sector*2048,size)
    added_hash=zlib.crc32(b'UX900.IFF')&0xffffffff
    assert hashes==sorted([original_hash,added_hash])
    assert resources[original_hash]==iff and resources[added_hash]==iff
    assert not (root/'0A').exists() and not (root/'0B').exists()
    before=(root/'assets.map').read_bytes();prepare(root);assert (root/'assets.map').read_bytes()==before


def test_direct_folder_loads_components_without_packed_blocks_or_binary_caches(tmp_path):
    import json,shutil
    from direct_folder import DirectFolder
    from prepare_direct_assets import prepare_direct
    source=tmp_path/'disc';archive,iff=make_disc(source);archive=bytearray(archive)
    encoded=encode_literals(bytes(range(64)),None);header=bytearray(iff[:128]);struct.pack_into('>I',header,8,128+len(encoded));struct.pack_into('>I',header,56,len(encoded))
    packed=bytes(header)+encoded+b'opaque trailer';struct.pack_into('>I',archive,52,len(packed));archive[2048:2048+len(packed)]=packed;(source/'0A').write_bytes(archive)
    root=tmp_path/'game';manifest=import_disc(source,root,False)
    # Migrate only loader metadata, then remove all legacy storage in this
    # synthetic fixture. The second startup must have no binary dependencies.
    DirectFolder(root)
    for stored in (root/'assets').rglob('*.stored'):
        assert stored.resolve().is_relative_to((tmp_path/'game/assets').resolve());stored.unlink()
    for name in ('_archive','_cache'):
        path=(root/name).resolve();assert path.is_relative_to((tmp_path/'game').resolve());shutil.rmtree(path)
    entry=manifest['entries'][0];layout=json.loads((root/entry['folder']/'asset.json').read_text());component=layout['blocks'][0]['components'][1];path=root/entry['folder']/component['path'];modified=bytearray(path.read_bytes());modified[7]^=255;path.write_bytes(modified)
    plan=prepare_direct(root)
    assert all(not s['path'].endswith('.stored') and not s['path'].startswith('_cache/') for s in plan['segments'])
    offset,size=plan['entries'][entry['hash']];visible=scatter_read(root,offset,size);parsed=iff_layout(visible);block=parsed['blocks'][0]
    expected=bytearray(range(64));expected[39]^=255
    assert visible[block['start']:block['start']+block['size']]==expected
    assert block['size']==block['logical']==64 and visible.endswith(b'opaque trailer')
    assert any(s['path']==path.relative_to(root).as_posix() for s in plan['segments'])
    first=(root/'assets.map').read_bytes();prepare_direct(root);assert (root/'assets.map').read_bytes()==first


def test_modern_import_has_no_packed_storage_or_archive_dependency(tmp_path):
    source=tmp_path/'disc';make_disc(source);root=tmp_path/'game'
    manifest=import_disc(source,root,False,direct=True)
    assert manifest['storage']=='loose-resources' and manifest['loader_metadata']['platform']=='xbox360'
    assert 'segments' not in manifest and 'parts' not in manifest
    assert not (root/'_archive').exists() and not list(root.rglob('*.stored'))
    assert all('.stored' not in line and '_cache/' not in line for line in (root/'assets.map').read_text().splitlines())
    prepare(root)


def test_fresh_direct_import_materializes_paired_components_without_payloads(tmp_path):
    import json,zlib
    from xbox_asset_edits import SourceReader
    from direct_folder import DirectFolder
    source=tmp_path/'disc';source.mkdir();(source/'default.xex').write_bytes(b'XEX2 fixture')
    name='fixture.bin';data_hash=zlib.crc32(name.upper().encode())&0xffffffff;meta_hash=0x11112222
    raw=b'CPU-DATA';packed=b'ZLIB'+struct.pack('>III',len(raw),16+len(zlib.compress(raw)),0)+zlib.compress(raw);body=b'GAP!'+packed+b'GPU!TAIL'
    head=bytearray(256);struct.pack_into('>II',head,0,0xf0985030,256);struct.pack_into('>I',head,24,1)
    for field,target in ((32,112),(36,160),(104,120),(112,144)):struct.pack_into('>I',head,field,target-field+1)
    struct.pack_into('>II',head,120,0x12345678,0x12345678);struct.pack_into('>4I',head,144,4,len(packed),4+len(packed),4);head[160:160+len(name)*2]=name.encode('utf-16-be')
    archive=bytearray(6144);struct.pack_into('>6I',archive,0,0xaa00b3bf,2048,1,0,2,0);struct.pack_into('>II8s',archive,24,3,0,'0A'.encode('utf-16-be').ljust(8,b'\0'))
    for i,row in enumerate(sorted(((meta_hash,1,0,len(head)),(data_hash,2,0,len(body))))):struct.pack_into('>4I',archive,40+i*16,*row)
    archive[2048:2304]=head;archive[4096:4096+len(body)]=body;(source/'0A').write_bytes(archive)
    root=tmp_path/'game';manifest=import_disc(source,root,False,direct=True)
    assert not list((root/'assets').rglob('payload.dat')) and not list((root/'assets').rglob('*.stored'))
    reader=SourceReader(root);assert reader.blocks(dict(bank=meta_hash,record=0))[1]==[raw,b'GPU!']
    plan=DirectFolder(root).plan();entry=next(e for e in manifest['entries'] if e['hash']==data_hash);offset,size=plan['entries'][data_hash]
    assert scatter_read(root,offset,size)==b'GAP!CPU-DATAGPU!TAIL'
    prepare(root);assert not (root/'_cache').exists()


def test_iso_reader_is_bounded_and_read_only(tmp_path):
    from xbox_disc_source import ISOReader
    image=tmp_path/'synthetic.iso';image.write_bytes(b'prefixPAYLOADsuffix')
    with ISOReader(image,6,7) as reader:
        assert reader.read(100)==b'PAYLOAD'
        assert reader.read()==b''
        reader.seek(-3,2);assert reader.read()==b'OAD'
        with pytest.raises(ValueError):reader.seek(8)


def test_native_dds_edit_never_rebuilds_guest_archive(tmp_path):
    source=tmp_path/'disc';source.mkdir();(source/'default.xex').write_bytes(b'XEX2 fixture')
    cpu=texture();header=bytearray(96)
    struct.pack_into('>8I',header,0,0xFF3BEF94,96,96+len(cpu),0,1,0,1,64-28+1)
    struct.pack_into('>8I',header,32,0,0xBB05A9C1,0,len(cpu),0,96,len(cpu),0)
    struct.pack_into('>I',header,64,68-64+1)
    struct.pack_into('>4I',header,68,0x12345678,0x5C369069,1,0)
    iff=bytes(header)+cpu;size=(2048+len(iff)+2047)&~2047
    archive=bytearray(size)
    struct.pack_into('>6I',archive,0,0xAA00B3BF,2048,1,0,1,0)
    struct.pack_into('>II8s',archive,24,size//2048,0,'0A'.encode('utf-16-be').ljust(8,b'\0'))
    struct.pack_into('>4I',archive,40,0x11112222,1,0,len(iff));archive[2048:2048+len(iff)]=iff
    (source/'0A').write_bytes(archive)
    root=tmp_path/'game';manifest=import_disc(source,root)
    assert (root/'native_dds.index').read_text().splitlines()==['CH2K8_DDS_V1','']
    dds=next((root/'assets').rglob('texture.dds'));value=bytearray(dds.read_bytes());value[128]^=0xff;dds.write_bytes(value)
    prepare(root)
    index=(root/'native_dds.index').read_text().splitlines()
    assert len(index)==2 and index[1].split('\t')[:3]==['32','32','18']
    assert scatter_read(root,0,size)==bytes(archive)
    assert not list((root/'_cache').glob('*.dat'))
    checker=Path(__file__).resolve().parents[1]/'port/out/build/win-amd64-vulkan/ch2k8_assets_check.exe'
    if checker.exists():
        result=subprocess.run([str(checker),'catalog',str(root)],capture_output=True,text=True)
        assert result.returncode==0,result.stderr
        assert '1 active replacements' in result.stdout
    struct.pack_into('<II',value,12,64,64);value=value[:128]+bytearray(64*64//2);dds.write_bytes(value)
    prepare(root)
    assert scatter_read(root,0,size)==bytes(archive)
    good=(root/'native_dds.index').read_bytes();dds.write_bytes(value[:-1])
    with pytest.raises(ValueError,match='payload'):prepare(root)
    assert (root/'native_dds.index').read_bytes()==good
