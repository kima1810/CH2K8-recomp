"""Native asset tool parity against the independent development implementation."""
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import zlib
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[1]
TOOL=ROOT/'port/out/build/win-amd64-vulkan/ch2k8_tools.exe'
sys.path[:0]=[str(ROOT/'tools')]
from loose_assets import import_disc, prepare, encode_literals
from test_loose_assets import make_disc, texture, scatter_read
from test_launcher_import import make_iso

pytestmark=pytest.mark.skipif(not TOOL.is_file(),reason='Build the ch2k8_tools native target')
IDENTITY=hashlib.sha256(b'XEX2 fixture').hexdigest()


def run(*args):
    environment=dict(os.environ,PATH=str(Path(os.environ['SystemRoot'])/'System32'),PYTHONHOME='Z:/bad',PYTHONPATH='Z:/bad')
    return subprocess.run([str(TOOL),*map(str,args)],capture_output=True,text=True,env=environment,timeout=60)


def fixture_disc(root,kind):
    if kind=='paired':
        root.mkdir();(root/'default.xex').write_bytes(b'XEX2 fixture')
        name='fixture.bin';data_hash=zlib.crc32(name.upper().encode())&0xffffffff;meta_hash=0x11112222
        raw=b'CPU-DATA';packed=b'ZLIB'+struct.pack('>III',len(raw),16+len(zlib.compress(raw)),0)+zlib.compress(raw);body=b'GAP!'+packed+b'GPU!TAIL'
        head=bytearray(256);struct.pack_into('>II',head,0,0xf0985030,256);struct.pack_into('>I',head,24,1)
        for field,target in ((32,112),(36,160),(104,120),(112,144)):struct.pack_into('>I',head,field,target-field+1)
        struct.pack_into('>II',head,120,0x12345678,0x12345678);struct.pack_into('>4I',head,144,4,len(packed),4+len(packed),4);head[160:160+len(name)*2]=name.encode('utf-16-be')
        archive=bytearray(6144);struct.pack_into('>6I',archive,0,0xaa00b3bf,2048,1,0,2,0);struct.pack_into('>II8s',archive,24,3,0,'0A'.encode('utf-16-be').ljust(8,b'\0'))
        for i,row in enumerate(sorted(((meta_hash,1,0,len(head)),(data_hash,2,0,len(body))))):struct.pack_into('>4I',archive,40+i*16,*row)
        archive[2048:2304]=head;archive[4096:4096+len(body)]=body;(root/'0A').write_bytes(archive)
        return
    archive,iff=make_disc(root)
    if kind in ('h7a','zlib'):
        data=bytes(range(64))
        encoded=encode_literals(data,None) if kind=='h7a' else b'ZLIB'+struct.pack('>III',len(data),16+len(zlib.compress(data)),0)+zlib.compress(data)
        header=bytearray(iff[:128]);struct.pack_into('>I',header,8,128+len(encoded));struct.pack_into('>I',header,56,len(encoded));iff=bytes(header)+encoded+b'opaque trailer'
    if kind=='texture':
        cpu=texture();header=bytearray(96)
        struct.pack_into('>8I',header,0,0xff3bef94,96,96+len(cpu),0,1,0,1,64-28+1)
        struct.pack_into('>8I',header,32,0,0xbb05a9c1,0,len(cpu),0,96,len(cpu),0)
        struct.pack_into('>I',header,64,68-64+1);struct.pack_into('>4I',header,68,0x12345678,0x5c369069,1,0)
        iff=bytes(header)+cpu
    size=(2048+len(iff)+2047)&~2047
    archive=bytearray(archive[:56])+bytearray(size-56)
    struct.pack_into('>I',archive,24,size//2048);struct.pack_into('>I',archive,52,len(iff));archive[2048:2048+len(iff)]=iff
    (root/'0A').write_bytes(archive)


def compare(a,b):
    assert (a/'assets.map').read_text()==(b/'assets.map').read_text()
    for name in ('native_dds.index','native_audio.index'):
        assert (a/name).read_bytes()==(b/name).read_bytes()
    for line in (a/'assets.map').read_text().splitlines()[1:]:
        kind,offset,size,relative=line.split('\t')
        if kind=='S':assert (a/relative).read_bytes()==(b/relative).read_bytes()


@pytest.mark.parametrize('kind',['standard','h7a','zlib','texture','paired'])
def test_native_import_and_maps_match_development_reference(tmp_path,kind):
    source=tmp_path/'disc';fixture_disc(source,kind)
    reference=tmp_path/'reference';import_disc(source,reference,direct=True)
    native=tmp_path/'native \u00e9 [test]'
    result=run('import',source,native,'--expected-xex-sha256',IDENTITY)
    assert result.returncode==0,result.stderr
    compare(reference,native)
    assert json.loads((reference/'assets.json').read_text())==json.loads((native/'assets.json').read_text())
    assert not list(native.rglob('*.stored')) and not (native/'0A').exists()
    if kind=='texture':
        ref_dds=next(reference.rglob('texture.dds'));native_dds=next(native.rglob('texture.dds'))
        assert ref_dds.read_bytes()==native_dds.read_bytes()
        data=bytearray(ref_dds.read_bytes());data[128]^=0xff
        ref_dds.write_bytes(data);native_dds.write_bytes(data)
        prepare(reference);result=run('prepare',native)
        assert result.returncode==0,result.stderr
        compare(reference,native)
        old=(native/'native_dds.index').read_bytes();native_dds.write_bytes(data[:-1])
        assert run('prepare',native).returncode!=0
        assert (native/'native_dds.index').read_bytes()==old
    if kind=='standard':
        component=next(native.rglob('*.rost'))/'block0.dat'
        relative=component.relative_to(native)
        data=bytearray(component.read_bytes());data[3]^=0xff
        component.write_bytes(data);(reference/relative).write_bytes(data)
        prepare(reference);assert run('prepare',native).returncode==0
        compare(reference,native)
        old=(native/'assets.map').read_bytes();component.write_bytes(data+b'bad resize')
        assert run('prepare',native).returncode!=0
        assert (native/'assets.map').read_bytes()==old


@pytest.mark.parametrize('base',[0,0xFD90000,0x2080000,0x18300000,0x500000])
def test_native_iso_layouts_transaction_and_identity(tmp_path,base):
    image=make_iso(tmp_path,base);before=hashlib.sha256(image.read_bytes()).digest()
    output=tmp_path/'installation'
    assert run('import',image,output).returncode!=0 and not output.exists()
    result=run('import',image,output,'--expected-xex-sha256',IDENTITY)
    assert result.returncode==0,result.stderr
    assert run('import',image,output,'--expected-xex-sha256',IDENTITY).returncode!=0
    assert hashlib.sha256(image.read_bytes()).digest()==before
    cancel=tmp_path/'cancel';cancel.write_text('cancel')
    failed=tmp_path/'cancelled'
    assert run('import',image,failed,'--expected-xex-sha256',IDENTITY,'--cancel-file',cancel).returncode!=0
    assert not failed.exists() and not list(tmp_path.glob('.ch2k8-import-*'))


def single_bank(root, blocks, kind):
    root.mkdir();(root/'default.xex').write_bytes(b'XEX2 fixture')
    count=len(blocks);table=32+count*32;record=table+4;header_size=(record+12+count*4+15)&~15
    h=bytearray(header_size);total=header_size+sum(map(len,blocks))
    struct.pack_into('>8I',h,0,0xff3bef94,header_size,total,0,count,0,1,table-28+1)
    cursor=header_size
    for i,b in enumerate(blocks):
        struct.pack_into('>8I',h,32+i*32,0,0xbb05a9c1,0,len(b),0,cursor,len(b),0);cursor+=len(b)
    struct.pack_into('>I',h,table,record-table+1)
    struct.pack_into('>3I',h,record,0x12345678,kind,count)
    iff=bytes(h)+b''.join(blocks);size=(2048+len(iff)+2047)&~2047
    archive=bytearray(size);struct.pack_into('>6I',archive,0,0xaa00b3bf,2048,1,0,1,0)
    struct.pack_into('>II8s',archive,24,size//2048,0,'0A'.encode('utf-16-be').ljust(8,b'\0'))
    struct.pack_into('>4I',archive,40,0x11112222,1,0,len(iff));archive[2048:2048+len(iff)]=iff
    (root/'0A').write_bytes(archive)


@pytest.mark.parametrize('kind',['scene','pcm','growing_roster','added_bank'])
def test_native_extended_edit_protocol_matches_reference(tmp_path,kind):
    from xbox_texture import export_dds
    source=tmp_path/'disc'
    if kind=='scene':
        original=texture();descriptor=bytearray(original[:224]);struct.pack_into('>I',descriptor,0x6c,1)
        scene=bytearray(64+224);struct.pack_into('>II',scene,0x20,1,64-0x24+1);scene[64:]=descriptor
        blocks=[bytes(scene),original[0x1000:]];single_bank(source,blocks,0xe26c9b5d)
    elif kind=='pcm':
        head=struct.pack('>11I',1,5,2,8,22050,0,2048,0,32,0,0)
        single_bank(source,[head,bytes(range(256))*8],0x1aedda1f)
    elif kind=='growing_roster':single_bank(source,[bytes(range(32))],0xc61649b2)
    else:make_disc(source)
    reference=tmp_path/'reference';import_disc(source,reference,direct=True)
    native=tmp_path/'native';result=run('import',source,native,'--expected-xex-sha256',IDENTITY)
    assert result.returncode==0,result.stderr
    for root in (reference,native):
        metadata=json.loads((root/'assets.json').read_text());entry=metadata['entries'][0]
        bank=root/entry['folder'];layout=json.loads((bank/'asset.json').read_text())
        if kind=='scene':
            dds=bytearray(export_dds(descriptor,blocks[1]));dds[128]^=0xff
            (bank/layout['records'][0]['folder']/'texture_0000.dds').write_bytes(dds)
        elif kind=='pcm':
            import wave
            with wave.open(str(bank/layout['records'][0]['folder']/'audio.wav'),'wb') as audio:
                audio.setparams((1,2,22050,8,'NONE','not compressed'));audio.writeframes(bytes(range(16)))
        elif kind=='growing_roster':
            component=bank/layout['blocks'][0]['components'][0]['path'];component.write_bytes(component.read_bytes()+b'\0\0')
        else:
            shutil.copytree(bank,root/'assets/uh901.iff')
            registry=dict(version=1,platform='xbox360',edits=[],banks=[dict(name='uh901.iff',folder='assets/uh901.iff',template=entry['hash'])])
            (root/'asset_edits.json').write_text(json.dumps(registry))
    prepare(reference);result=run('prepare',native)
    assert result.returncode==0,result.stderr
    compare(reference,native)
    if kind=='pcm':assert len((native/'native_audio.index').read_text().splitlines())==2
    if kind=='scene':assert len((native/'native_dds.index').read_text().splitlines())==2


def test_native_failed_import_removes_only_owned_staging(tmp_path):
    source=tmp_path/'disc';fixture_disc(source,'h7a')
    archive=bytearray((source/'0A').read_bytes());archive[2048+128+8]^=0x10
    (source/'0A').write_bytes(archive);before=hashlib.sha256(archive).digest()
    unrelated=tmp_path/'keep';unrelated.mkdir();(unrelated/'edits').write_text('keep')
    target=tmp_path/'failed'
    result=run('import',source,target,'--expected-xex-sha256',IDENTITY)
    assert result.returncode!=0
    assert not target.exists() and not list(tmp_path.glob('.ch2k8-import-*'))
    assert (unrelated/'edits').read_text()=='keep'
    assert hashlib.sha256((source/'0A').read_bytes()).digest()==before
