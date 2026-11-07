"""Import Xbox archives as folders; prepare DDS edits without rebuilding 0A..0M.

The compatibility address space is a read-only scatter map, not an archive file.
Original metadata and unknown bytes are preserved. Source files are never edited.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import shutil
import struct
import ctypes
import os
from pathlib import Path

from ch2k8_archive import open_archive, load_names
from xbox_texture import export_dds, apply_dds, describe

_codec = None
for _path in [Path(__file__).resolve().parents[1]/'ch2k8_asset_codec.dll', Path(__file__).resolve().parents[1]/'port/out/build/win-amd64-vulkan/ch2k8_asset_codec.dll']:
    if _path.is_file():
        _codec=ctypes.CDLL(str(_path))
        _codec.ch2k8_h7a.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p,ctypes.c_size_t]
        _codec.ch2k8_h7a.restype=ctypes.c_int
        _codec.ch2k8_fnv64.argtypes=[ctypes.c_void_p,ctypes.c_size_t]
        _codec.ch2k8_fnv64.restype=ctypes.c_uint64
        break


def fnv64(data):
    if _codec:
        return format(_codec.ch2k8_fnv64(data,len(data)),'016x')
    value=14695981039346656037
    for b in data:
        value=((value^b)*1099511628211)&0xFFFFFFFFFFFFFFFF
    return format(value,'016x')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def safe(value):
    result = re.sub(r'[^A-Za-z0-9_.-]', '_', value).strip('.')
    return result if result and result.upper().split('.')[0] not in {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(10)), *(f'LPT{i}' for i in range(10))} else '_' + result


def decode(data, logical):
    if data[:4] == bytes.fromhex('0e4837c3'):
        if len(data) < 20:
            raise ValueError('short H7A header')
        expected, stored, _, shift = struct.unpack_from('>4I', data, 4)
        if expected != logical or stored != len(data) or not 1 <= shift <= 16:
            raise ValueError('invalid H7A header')
        if _codec:
            result=ctypes.create_string_buffer(logical)
            if not _codec.ch2k8_h7a(data,len(data),result,logical):
                raise ValueError('invalid H7A stream')
            return result.raw
        out = bytearray()
        pos = 20
        while len(out) < logical:
            if pos >= len(data):
                raise ValueError('truncated H7A flags')
            flags = data[pos]
            pos += 1
            for bit in range(8):
                if len(out) >= logical:
                    break
                if flags & (1 << bit):
                    if pos + 2 > len(data):
                        raise ValueError('truncated H7A match')
                    token = int.from_bytes(data[pos:pos+2], 'big')
                    pos += 2
                    distance = token & ((1 << shift)-1)
                    length = min((token >> shift)+3, logical-len(out))
                    if not 1 <= distance <= len(out):
                        raise ValueError('invalid H7A distance')
                    chunk = out[-distance:][:min(distance, length)]
                    out.extend((chunk*((length+len(chunk)-1)//len(chunk)))[:length])
                else:
                    if pos >= len(data):
                        raise ValueError('truncated H7A literal')
                    out.append(data[pos])
                    pos += 1
        return bytes(out)
    if data[:4] == b'ZLIB':
        import zlib
        result = zlib.decompress(data[16:])
    else:
        result = data
    if len(result) != logical:
        raise ValueError('decoded block size mismatch')
    return result


def encode_literals(data, original):
    """Preserve the source codec/opaque wrapper fields; H7A uses literals."""
    unknown,shift=0,12
    if original is not None:
        if original[:4]==b'ZLIB':
            import zlib
            body=zlib.compress(data)
            header=bytearray(original[:16])
            struct.pack_into('>II',header,4,len(data),16+len(body))
            return bytes(header)+body
        if original[:4]!=bytes.fromhex('0e4837c3'):
            return data
        unknown,shift=struct.unpack_from('>II',original,12)
    chunks = [b'\0' + data[i:i+8] for i in range(0, len(data), 8)]
    body = b''.join(chunks)
    return struct.pack('>5I', 0x0E4837C3, len(data), 20+len(body), unknown, shift) + body


def iff_layout(data):
    if len(data) < 32 or data[:4] != bytes.fromhex('ff3bef94'):
        return None
    header, length = struct.unpack_from('>II', data, 4)
    bc = struct.unpack_from('>I', data, 16)[0]
    rc = struct.unpack_from('>I', data, 24)[0]
    table = 28 + struct.unpack_from('>I', data, 28)[0] - 1
    if not 32 <= header <= length <= len(data) or 32+bc*32 > header or not 32+bc*32 <= table <= header-rc*4:
        raise ValueError('invalid IFF boundaries')
    blocks = []
    for i in range(bc):
        fields = struct.unpack_from('>8I', data, 32+i*32)
        start, size = fields[5:7]
        if start < header or start+size > length:
            raise ValueError('invalid IFF block')
        blocks.append(dict(index=i, start=start, size=size, logical=fields[3]))
    if any(a['start']+a['size'] > b['start'] for a,b in zip(sorted(blocks,key=lambda b:b['start']), sorted(blocks,key=lambda b:b['start'])[1:])):
        raise ValueError('overlapping IFF blocks')
    records = []
    for i in range(rc):
        field = table+i*4
        off = field+struct.unpack_from('>I', data, field)[0]-1
        if not table+rc*4 <= off <= header-12:
            raise ValueError('invalid IFF record')
        ident, kind, count = struct.unpack_from('>3I', data, off)
        if count > bc or off+12+4*count > header:
            raise ValueError('invalid IFF record offsets')
        offsets = list(struct.unpack_from(f'>{count}I', data, off+12))
        if any(v != 0xFFFFFFFF and v > blocks[j]['logical'] for j,v in enumerate(offsets)):
            raise ValueError('IFF record exceeds decoded block')
        records.append(dict(index=i, id=ident, type=kind, offsets=offsets))
    return dict(header=header, length=length, blocks=blocks, records=records)


def explode(data, folder, textures=True, preserve_packed=True):
    layout = iff_layout(data)
    pieces = []
    def piece(start, end, name, write=True):
        if end > start:
            if write:(folder/name).write_bytes(data[start:end])
            pieces.append(dict(offset=start, size=end-start, path=name))
    if layout is None:
        piece(0, len(data), 'payload.dat')
        return dict(pieces=pieces, textures=[])
    cursor = 0
    for block in sorted(layout['blocks'], key=lambda b:b['start']):
        piece(cursor, block['start'], f'gap_{cursor:08x}.dat')
        block['path'] = f"block_{block['index']:02d}.stored"
        piece(block['start'], block['start']+block['size'], block['path'],preserve_packed)
        cursor = block['start']+block['size']
    piece(cursor, len(data), 'tail.dat')
    layout['pieces'] = pieces
    layout['textures'] = []
    layout['unsupported_textures'] = []
    decoded = {}
    types = {0x5C369069:'txtr', 0xE26C9B5D:'scne', 0x86A1AC9E:'layt',0xC61649B2:'rost',0x68B693B2:'name',0xA7701F00:'cdan',0x1AEDDA1F:'audo'}
    for block in layout['blocks']:
        j=block['index']
        decoded[j]=decode(data[block['start']:block['start']+block['size']],block['logical'])
        block['components']=[]
        offsets=sorted({r['offsets'][j] for r in layout['records'] if len(r['offsets'])>j and r['offsets'][j]!=0xFFFFFFFF} | {0,block['logical']})
        for start,end in zip(offsets,offsets[1:]):
            owners=[r for r in layout['records'] if len(r['offsets'])>j and r['offsets'][j]==start]
            name=(f"{owners[0]['index']:04d}_{owners[0]['id']:08x}."+types.get(owners[0]['type'],format(owners[0]['type'],'08x')) if owners else '_unclaimed')
            child=folder/name
            child.mkdir(exist_ok=True)
            path=f'{name}/block{j}.dat'
            value=decoded[j][start:end]
            (folder/path).write_bytes(value)
            block['components'].append(dict(start=start,end=end,path=path,sha256=digest(value)))
    for record in layout['records']:
        extension = types.get(record['type'], format(record['type'], '08x'))
        record['folder'] = f"_{record['id']:08x}.{extension}"
        # A record index disambiguates aliases without silently overwriting.
        record['folder'] = f"{record['index']:04d}" + record['folder']
        child = folder/record['folder']
        child.mkdir(exist_ok=True)
        write_json(child/'record.json', record)
        if not textures or record['type'] != 0x5C369069:
            continue
        spans = []
        for j,start in enumerate(record['offsets']):
            if start == 0xFFFFFFFF:
                continue
            ends = [r['offsets'][j] for r in layout['records'] if len(r['offsets']) > j and r['offsets'][j] != 0xFFFFFFFF and r['offsets'][j] > start]
            spans.append((j,start,min(ends,default=layout['blocks'][j]['logical'])))
        try:
            if len(spans) not in (1,2):
                raise ValueError('unsupported TXTR component count')
            j,start,end = spans[0]
            if j not in decoded:
                block = layout['blocks'][j]
                decoded[j] = decode(data[block['start']:block['start']+block['size']],block['logical'])
            cpu = decoded[j][start:end]
            gpu=None if len(spans)==1 else decoded[spans[1][0]][spans[1][1]:spans[1][2]]
            dds = export_dds(cpu,gpu)
            info=describe(cpu,gpu)
            if gpu is None and apply_dds(cpu,dds) != cpu:
                raise ValueError('DDS round trip differs')
            path = record['folder']+'/texture.dds'
            (folder/path).write_bytes(dds)
            layout['textures'].append(dict(path=path, sha256=digest(dds), block=j, start=start, end=end, identity=fnv64(dds[128:]), descriptor=info))
        except ValueError as exc:
            layout['unsupported_textures'].append(dict(record=record['index'], reason=str(exc)))
    return layout


def import_disc(source, output, textures=True, direct=False, progress=None):
    if output.exists():
        raise ValueError('output already exists; choose a new installation directory')
    if source.is_file():
        from xbox_disc_source import XboxISO
        source=XboxISO(source)
    archive = open_archive(source,load_names([]))
    if not (source/'default.xex').is_file():
        raise ValueError('Xbox default.xex missing')
    output.mkdir(parents=True)
    (output/'assets').mkdir()
    if not direct:(output/'_archive').mkdir()
    with (source/'default.xex').open('rb') as original,(output/'default.xex').open('xb') as copied:
        shutil.copyfileobj(original,copied,8<<20)
    manifest = dict(version=1, platform='xbox360', total=archive.total, parts=[], entries=[], segments=[])
    base = 0
    for p in archive.parts:
        manifest['parts'].append(dict(name=p.name, offset=base, size=p.units*0x800))
        base += p.units*0x800
    if direct:
        from direct_folder import compatibility_metadata
        count=len(archive.parts);header=archive.read(0,24+count*16+len(archive.entries)*16)
        entries=[dict(index=e.index,hash=e.hash) for e in archive.entries]
        manifest['loader_metadata']=compatibility_metadata(header,entries,count,manifest['parts'][0]['size'])
        manifest['storage']='loose-resources'
    cursor = 0
    for e in sorted(archive.entries,key=lambda e:e.offset):
        if progress:progress(len(manifest['entries']),len(archive.entries))
        if e.offset < cursor:
            raise ValueError('overlapping archive entries')
        while not direct and cursor < e.offset:
            n = min(8<<20,e.offset-cursor)
            path = f'_archive/gap_{cursor:012x}.dat'
            (output/path).write_bytes(archive.read(cursor,n))
            manifest['segments'].append(dict(offset=cursor,size=n,path=path))
            cursor += n
        data = archive.read(e.offset,e.size)
        name = safe(e.name or f'hash_{e.hash:08x}.iff')
        folder = output/'assets'/name
        if folder.exists():
            raise ValueError(f'duplicate archive asset folder: {name}')
        folder.mkdir()
        layout = explode(data, folder, textures,preserve_packed=not direct)
        write_json(folder/'asset.json', layout)
        manifest['entries'].append(dict(index=e.index,hash=e.hash,offset=e.offset,size=e.size,folder='assets/'+name,sha256=digest(data)))
        if not direct:
            for p in layout['pieces']:
                manifest['segments'].append(dict(offset=e.offset+p['offset'],size=p['size'],path='assets/'+name+'/'+p['path']))
        cursor = e.offset+e.size
        if len(manifest['entries']) % 100 == 0:
            print(f"Imported {len(manifest['entries'])}/{len(archive.entries)}",flush=True)
    while not direct and cursor < archive.total:
        n = min(8<<20,archive.total-cursor)
        path=f'_archive/gap_{cursor:012x}.dat'
        (output/path).write_bytes(archive.read(cursor,n))
        manifest['segments'].append(dict(offset=cursor,size=n,path=path))
        cursor += n
    if direct:
        manifest.pop('segments');manifest.pop('parts')
    if progress:progress(len(archive.entries),len(archive.entries))
    write_json(output/'assets.json',manifest)
    if direct:
        from materialize_paired import materialize
        materialize(output,keep_originals=False)
    if progress:progress(len(archive.entries),len(archive.entries))
    if not direct:write_map(output,manifest)
    prepare(output)
    return manifest


def contained(root, relative):
    p = (root/relative).resolve()
    if not p.is_relative_to(root.resolve()):
        raise ValueError('asset path escapes installation')
    return p


class FolderSnapshot:
    """One bounded directory walk instead of per-file canonical path walks.

    Windows DirEntry carries size/timestamps from FindFirstFile. Reject reparse
    points while walking, so cached paths cannot follow junctions/symlinks.
    """
    def __init__(self,root):
        self.root=root
        self.files={}
        self.directories={'.':root}
        pending=[root]
        while pending:
            parent=pending.pop()
            with os.scandir(parent) as entries:
                for entry in entries:
                    info=entry.stat(follow_symlinks=False)
                    if entry.is_symlink() or getattr(info,'st_file_attributes',0)&0x400:
                        raise ValueError('Linked paths are not supported in a loose installation: '+entry.path)
                    path=Path(entry.path)
                    key=path.relative_to(root).as_posix().casefold()
                    if entry.is_dir(follow_symlinks=False):
                        if parent!=root or entry.name in ('assets','_archive'):
                            self.directories[key]=path
                            pending.append(path)
                    elif entry.is_file(follow_symlinks=False):
                        self.files[key]=(path,info)
    def key(self,path):
        if path.is_absolute():path=path.relative_to(self.root)
        if path.is_absolute() or '..' in path.parts:
            raise ValueError('Asset path escapes installation')
        return path.as_posix().casefold()
    def directory(self,path):
        return self.directories[self.key(Path(path))]
    def file(self,path):
        return self.files[self.key(Path(path))]


def write_map(root, manifest, snapshot=None):
    lines = ['CH2K8_LOOSE_V1']
    for p in manifest['parts']:
        lines.append(f"P\t{p['offset']}\t{p['size']}\t{p['name']}")
    end = 0
    for s in sorted(manifest['segments'],key=lambda s:s['offset']):
        if s['offset'] != end or not s['size'] > 0 or any(c in s['path'] for c in '\t\r\n'):
            raise ValueError('invalid scatter-map coverage')
        if snapshot and snapshot.key(Path(s['path'])) in snapshot.files:
            actual_size=snapshot.file(s['path'])[1].st_size
        else:
            actual_size=contained(root,s['path']).stat().st_size
        if actual_size != s['size']:
            raise ValueError('scatter-map file size mismatch')
        lines.append(f"S\t{s['offset']}\t{s['size']}\t{s['path']}")
        end += s['size']
    if end != sum(p['size'] for p in manifest['parts']):
        raise ValueError('scatter map does not cover virtual archive')
    temporary = root/'assets.map.tmp'
    temporary.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    temporary.replace(root/'assets.map')


def prepare(root):
    """Validate loose components and publish native DDS catalog plus scatter map."""
    root=root.resolve()
    if json.loads((root/'assets.json').read_text(encoding='utf-8')).get('storage')=='loose-resources':
        from prepare_direct_assets import prepare_direct
        return prepare_direct(root)
    capabilities=root/'runtime_capabilities.json'
    if capabilities.is_file() and json.loads(capabilities.read_text(encoding='utf-8-sig')).get('direct_resources'):
        from prepare_direct_assets import prepare_direct
        return prepare_direct(root)
    snapshot=FolderSnapshot(root)
    manifest = json.loads(snapshot.file('assets.json')[0].read_text(encoding='utf-8'))
    if manifest['version'] != 1 or manifest['platform'] != 'xbox360':
        raise ValueError('unsupported asset installation')
    original_manifest=manifest
    if (root/'asset_edits.json').exists():
        from xbox_asset_edits import augment_manifest
        manifest=augment_manifest(root,manifest)
    added=[e for e in manifest['entries'] if e.get('added')]
    changes = {}
    catalog=[]
    identities={}
    cache=root/'_cache'
    cache.mkdir(exist_ok=True)
    state_path=cache/'validation.json'
    try:
        previous=json.loads(state_path.read_text(encoding='utf-8'))
    except (OSError,ValueError):
        previous={}
    stamps={}
    def inspect(path,validate=None):
        path,stat=snapshot.file(path)
        key=path.relative_to(root).as_posix()
        signature=[stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns]
        old=previous.get(key,{})
        if old.get('stat')==signature and isinstance(old.get('sha256'),str):
            stamps[key]=old
            return old['sha256'],None,stat.st_size
        payload=path.read_bytes()
        if validate:validate(payload)
        sha=digest(payload)
        stamps[key]=dict(stat=signature,sha256=sha)
        return sha,payload,len(payload)
    def save_stamps():
        temporary=cache/'validation.json.tmp'
        write_json(temporary,stamps)
        temporary.replace(state_path)
    for e in manifest['entries']:
        folder = snapshot.directory(e['folder'])
        layout = json.loads(snapshot.file(folder/'asset.json')[0].read_text(encoding='utf-8'))
        changed = []
        for t in layout['textures']:
            signature,_,_=inspect(folder/t['path'],lambda p:validate_dds(p,t['descriptor']))
            info=t['descriptor']
            path=e['folder']+'/'+t['path']
            key=(info['width'],info['height'],info['format'],t['identity'])
            if key in identities and identities[key]!=signature:
                raise ValueError(f'Ambiguous DDS replacements for identical source pixels: {path}')
            if key not in identities and signature!=t['sha256']:
                catalog.append('\t'.join(map(str,[info['width'],info['height'],info['format'],t['identity'],path])))
            identities[key]=signature
        for b in layout.get('blocks',[]):
            for component in b.get('components',[]):
                path=snapshot.file(folder/component['path'])[0]
                sha,payload,size=inspect(path)
                if size!=component['end']-component['start']:
                    whole_roster=(len(layout['records'])==1 and layout['records'][0]['type']==0xc61649b2 and component['start']==0 and component['end']==b['logical'] and len(b['components'])==1)
                    if not whole_roster or size<component['end'] or size%2 or size>64*1024*1024:
                        raise ValueError(f"Resource component resizing requires validated relocation: {folder/component['path']}")
                if sha!=component['sha256']:
                    if payload is None:payload=path.read_bytes()
                    changed.append((b,component,payload))
        if 'blocks' not in layout:
            # Opaque/CDF entries remain editable as whole-file payloads. Their
            # own internal offsets must be maintained by the editor.
            path=snapshot.file(folder/'payload.dat')[0]
            sha,payload,size=inspect(path)
            if sha!=e['sha256']:
                if payload is None:payload=path.read_bytes()
                cache=root/'_cache';cache.mkdir(exist_ok=True)
                path=f'_cache/{e["hash"]:08x}_{digest(payload)}.dat'
                (root/path).write_bytes(payload)
                changes[e['index']]=(path,len(payload))
        if not changed:
            continue
        raw = bytearray(e['size'])
        for p in layout['pieces']:
            value = contained(folder,p['path']).read_bytes()
            if len(value) != p['size']:
                raise ValueError('preserved IFF component size changed')
            raw[p['offset']:p['offset']+p['size']] = value
        if digest(raw) != e['sha256']:
            raise ValueError('preserved IFF components changed; only DDS editing is supported')
        blocks = {}
        for b,component,payload in changed:
            j = b['index']
            if j not in blocks:
                blocks[j] = bytearray(decode(raw[b['start']:b['start']+b['size']],b['logical']))
            blocks[j][component['start']:component['end']] = payload
        # Preserve all inter-block gaps, metadata and trailer; update only
        # stored block sizes/positions and file length. Record offsets stay fixed.
        out = bytearray()
        cursor = 0
        positions = {}
        for b in sorted(layout['blocks'],key=lambda b:b['start']):
            out.extend(raw[cursor:b['start']])
            original=raw[b['start']:b['start']+b['size']]
            value = encode_literals(bytes(blocks[b['index']]),original) if b['index'] in blocks else original
            positions[b['index']] = (len(out),len(value))
            out.extend(value)
            cursor = b['start']+b['size']
        out.extend(raw[cursor:])
        for j,(off,size) in positions.items():
            struct.pack_into('>II',out,32+j*32+20,off,size)
            if j in blocks:struct.pack_into('>I',out,32+j*32+12,len(blocks[j]))
        struct.pack_into('>I',out,8,layout['length']+len(out)-len(raw))
        iff_layout(out)
        cache = root/'_cache'
        cache.mkdir(exist_ok=True)
        path = f'_cache/{e["hash"]:08x}_{digest(out)}.dat'
        if not (root/path).exists():
            (root/path).write_bytes(out)
        changes[e['index']] = (path,len(out))
    pcm=[]
    if (root/'asset_edits.json').exists():
        from xbox_asset_edits import SourceReader
        extra_dds,pcm=SourceReader(root,original_manifest).native_edits(export_dds)
        from xbox_texture import FORMATS
        reverse={code:fmt for fmt,(code,size) in FORMATS.items()}
        for extra in extra_dds:
            old=extra['original'];h,w=struct.unpack_from('<II',old,12);fmt=reverse[old[84:88]]
            validate_dds(extra['data'],dict(width=w,height=h,format=fmt))
            key=(w,h,fmt,fnv64(old[128:]));signature=digest(extra['data'])
            if key in identities and identities[key]!=signature:raise ValueError('Conflicting native DDS content identities')
            if key not in identities and extra['data']!=old:catalog.append('\t'.join(map(str,[w,h,fmt,key[3],extra['path']])))
            identities[key]=signature
    pcm_rows=[];pcm_seen={}
    for item in pcm:
        key=(item['first_hash'],item['prefix_length'],item['prefix_hash'],item['channels'])
        signature=digest(contained(root,item['path']).read_bytes())
        if key in pcm_seen and pcm_seen[key]!=signature:raise ValueError('Conflicting native WAV content identities')
        if key not in pcm_seen:pcm_rows.append('\t'.join(map(str,[item['first_hash'],item['prefix_length'],item['prefix_hash'],item['channels'],item['rate'],item['samples'],item['path']])))
        pcm_seen[key]=signature
    temporary=root/'native_audio.index.tmp'
    temporary.write_text('CH2K8_PCM_V1\n'+'\n'.join(pcm_rows)+'\n',encoding='utf-8')
    temporary.replace(root/'native_audio.index')
    temporary=root/'native_dds.index.tmp'
    temporary.write_text('CH2K8_DDS_V1\n'+'\n'.join(catalog)+'\n',encoding='utf-8')
    temporary.replace(root/'native_dds.index')
    if not changes and not added:
        write_map(root,manifest,snapshot)
        save_stamps()
        print(f'Loose assets ready; {len(catalog)} native DDS replacements; no binary overlays.')
        return
    # Rebuild the small virtual TOC, never any archive chunks. The original
    # part count and all opaque header fields are retained.
    header_size = 24+len(manifest['parts'])*16+len(manifest['entries'])*16
    original_header_size=24+len(manifest['parts'])*16+len(original_manifest['entries'])*16
    first = next(s for s in manifest['segments'] if s['offset']==0)
    original_header = contained(root,first['path']).read_bytes()[:original_header_size]
    if len(original_header) != original_header_size:
        raise ValueError('archive header is not contiguous')
    prefix=24+len(manifest['parts'])*16
    header=bytearray(original_header[:prefix]);struct.pack_into('>I',header,16,len(manifest['entries']))
    original_by_hash={e['hash']:e for e in original_manifest['entries']}
    toc_offsets={}
    for e in sorted(manifest['entries'],key=lambda e:e['hash']):
        template=original_by_hash[e.get('template_hash',e['hash'])]
        unknown=struct.unpack_from('>I',original_header,prefix+template['index']*16+8)[0]
        toc_offsets[e['index']]=len(header)
        header.extend(struct.pack('>4I',e['hash'],0,unknown,e['size']))
    segments=[]
    cursor=(header_size+2047)&~2047
    def zero(size):
        if size:
            path=f'_cache/zero_{size}.dat'
            if not (root/path).exists():
                (root/path).write_bytes(bytes(size))
            segments.append(dict(offset=cursor,size=size,path=path))
    header_path='_cache/pending_header.dat'
    segments.append(dict(offset=0,size=header_size,path=header_path))
    save=cursor
    cursor=header_size
    zero(save-cursor)
    cursor=save
    for e in sorted(manifest['entries'],key=lambda e:e['offset']):
        off=toc_offsets[e['index']]
        size=changes.get(e['index'],('',e['size']))[1]
        struct.pack_into('>I',header,off+4,cursor//2048)
        struct.pack_into('>I',header,off+12,size)
        if e['index'] in changes:
            segments.append(dict(offset=cursor,size=size,path=changes[e['index']][0]))
        elif e.get('added'):
            layout=json.loads((contained(root,e['folder'])/'asset.json').read_text())
            for p in layout['pieces']:segments.append(dict(offset=cursor+p['offset'],size=p['size'],path=e['folder']+'/'+p['path']))
        else:
            for s in manifest['segments']:
                if e['offset'] <= s['offset'] < e['offset']+e['size']:
                    segments.append(dict(offset=cursor+s['offset']-e['offset'],size=s['size'],path=s['path']))
        cursor+=size
        padding=(-cursor)%2048
        zero(padding)
        cursor+=padding
    parts=[dict(p) for p in manifest['parts']]
    if cursor > sum(p['size'] for p in parts):
        growth=cursor-sum(p['size'] for p in parts)
        if parts[-1]['size']+growth>parts[0]['size']:
            raise ValueError('Edited resources exceed the supported 13-part virtual capacity')
        parts[-1]['size']+=growth
        struct.pack_into('>I',header,24+(len(parts)-1)*16,parts[-1]['size']//2048)
    # Retain capacity, but split trailing zeros to avoid creating huge files.
    end=sum(p['size'] for p in parts)
    while cursor<end:
        n=min(8<<20,end-cursor)
        zero(n)
        cursor+=n
    header_path=f'_cache/header_{digest(header)}.dat'
    segments[0]['path']=header_path
    (root/header_path).write_bytes(header)
    write_map(root,dict(parts=parts,segments=segments),snapshot)
    save_stamps()
    print(f'Loose assets ready; {len(catalog)} native DDS replacements, {len(changes)} binary overlays; no archive chunks rebuilt.')


def validate_dds(dds, original):
    """Strict legacy BC1/2/3 2D DDS, including larger native replacements."""
    if len(dds)<128 or dds[:4]!=b'DDS ' or struct.unpack_from('<I',dds,4)[0]!=124:
        raise ValueError('Invalid DDS header')
    h,w=struct.unpack_from('<II',dds,12)
    depth,mips=struct.unpack_from('<II',dds,24)
    mips=max(mips,1)
    pf,flags=struct.unpack_from('<II',dds,76)
    caps2=struct.unpack_from('<I',dds,112)[0]
    from xbox_texture import FORMATS
    fourcc,bpp=FORMATS[original['format']]
    if not 1<=w<=8192 or not 1<=h<=8192 or w%4 or h%4 or depth not in (0,1) or caps2 or pf!=32 or flags!=4 or dds[84:88]!=fourcc:
        raise ValueError('DDS must be a supported 2D BC texture with the original format')
    if w*original['height']!=h*original['width'] or w<original['width'] or w%original['width'] or (w//original['width']) & ((w//original['width'])-1):
        raise ValueError('DDS replacement must retain aspect ratio and use an integer power-of-two upscale')
    if mips>max(w,h).bit_length():
        raise ValueError('Too many DDS mip levels')
    expected=sum(((max(1,w>>i)+3)//4)*((max(1,h>>i)+3)//4)*bpp for i in range(mips))
    if len(dds)!=128+expected:
        raise ValueError('DDS mip payload length mismatch')
    return w,h,mips


def main():
    p=argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub=p.add_subparsers(dest='command',required=True)
    imp=sub.add_parser('import',help='import an Xbox ISO or extracted disc to a new loose installation')
    imp.add_argument('source',type=Path)
    imp.add_argument('output',type=Path)
    imp.add_argument('--no-textures',action='store_true',help='preserve all data but skip DDS export')
    prep=sub.add_parser('prepare',help='validate DDS edits and publish the runtime scatter map')
    prep.add_argument('root',type=Path)
    a=p.parse_args()
    if a.command=='import':
        import_disc(a.source,a.output,not a.no_textures,direct=True)
    else:
        prepare(a.root)


if __name__=='__main__':
    main()
