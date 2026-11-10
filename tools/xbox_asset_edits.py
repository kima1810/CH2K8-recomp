"""Standard-library-only Xbox folder edit protocol shared with the recomp.

No archive rebuilding or UI dependencies. Sidecars live in their owning assets
folders; the registry describes source identities for host DDS/PCM substitution.
"""
import json
import struct
import wave
import zlib
import copy
import re
from pathlib import Path


def decode_component(data,limit=128*1024*1024):
    """Decode one Xbox component on read; never writes a container."""
    if data[:4]==bytes.fromhex('0e4837c3'):
        if len(data)<20:raise ValueError('Short Xbox H7A component')
        expected,stored,unknown,shift=struct.unpack_from('>4I',data,4)
        if not 0<=expected<=limit or stored!=len(data) or not 1<=shift<=16:raise ValueError('Invalid Xbox H7A component header')
        out=bytearray();pos=20
        while len(out)<expected:
            if pos>=len(data):raise ValueError('Truncated Xbox H7A flags')
            flags=data[pos];pos+=1
            for bit in range(8):
                if len(out)>=expected:break
                if flags&(1<<bit):
                    if pos+2>len(data):raise ValueError('Truncated Xbox H7A match')
                    token=int.from_bytes(data[pos:pos+2],'big');pos+=2;distance=token&((1<<shift)-1);length=min((token>>shift)+3,expected-len(out))
                    if not 1<=distance<=len(out):raise ValueError('Invalid Xbox H7A distance')
                    start=len(out)-distance;chunk=out[start:start+min(distance,length)];out.extend((chunk*((length+len(chunk)-1)//len(chunk)))[:length])
                else:
                    if pos>=len(data):raise ValueError('Truncated Xbox H7A literal')
                    out.append(data[pos]);pos+=1
        return bytes(out)
    if data[:4]==b'ZLIB':
        if len(data)<16:raise ValueError('Short Xbox ZLIB component')
        expected,stored=struct.unpack_from('>II',data,4)
        if expected>limit or stored!=len(data):raise ValueError('Invalid Xbox ZLIB component header')
        decoder=zlib.decompressobj();out=decoder.decompress(data[16:],expected+1)
        if len(out)!=expected or not decoder.eof or decoder.unconsumed_tail:raise ValueError('Invalid Xbox ZLIB payload')
        return out
    return data


def fnv(data):
    value=14695981039346656037
    for b in data:value=((value^b)*1099511628211)&0xffffffffffffffff
    return f'{value:016x}'


def augment_manifest(root,manifest):
    marker=Path(root)/'asset_edits.json'
    registry=json.loads(marker.read_text()) if marker.exists() else dict(version=1,platform='xbox360')
    if registry.get('version')!=1 or registry.get('platform')!='xbox360':raise ValueError('Invalid native asset registry')
    result=copy.deepcopy(manifest);known={e['hash']:e for e in manifest['entries']};occupied=set(known)
    end=manifest['total']
    for spec in registry.get('banks',[]):
        name=spec['name']
        if not re.fullmatch(r'(?:sel)?u[haxyz][0-9]{3,4}\.iff',name):raise ValueError('Unsupported new Xbox uniform filename')
        identity=zlib.crc32(name.upper().encode('ascii'))&0xffffffff
        if identity in occupied:raise ValueError('Duplicate Xbox asset identity')
        template=known[int(spec['template'])]
        if spec['folder']!='assets/'+name:raise ValueError('New uniform folder/name mismatch')
        folder=(Path(root)/spec['folder']).resolve()
        if folder.parent!=(Path(root)/'assets').resolve():raise ValueError('New uniform folder escapes assets')
        layout=json.loads((folder/'asset.json').read_text())
        if not layout.get('blocks'):raise ValueError('New uniform banks require standard Xbox IFF components')
        entry=dict(template,index=max(e['index'] for e in result['entries'])+1,hash=identity,folder=spec['folder'],offset=end,added=True,template_hash=template['hash'])
        result['entries'].append(entry);end+=(template['size']+2047)&~2047;occupied.add(identity)
    if manifest.get('storage')=='loose-resources':
        assets=(Path(root)/'assets').resolve();folders={e['folder'] for e in result['entries']}
        for folder in sorted(assets.iterdir()):
            relative='assets/'+folder.name
            if relative in folders or not folder.is_dir() or not (folder/'asset.json').is_file():continue
            layout=json.loads((folder/'asset.json').read_text());spec=layout.get('identity')
            if not spec:continue
            name=spec['name']
            if name!=folder.name or not re.fullmatch(r'[a-z0-9_]{1,48}\.iff',name) or folder.resolve().parent!=assets:raise ValueError('Invalid loose asset folder identity')
            identity=zlib.crc32(name.upper().encode('ascii'))&0xffffffff
            if identity!=spec['hash'] or identity in occupied:raise ValueError('Duplicate or incorrect loose asset CRC identity')
            size=int(spec['source_size']);flags=int(spec['toc_flags'])
            if not layout.get('blocks') or not layout['length']<=size<=512*1024*1024 or not 0<=flags<=0xffffffff:raise ValueError('Invalid loose asset metadata')
            entry=dict(index=max(e['index'] for e in result['entries'])+1,hash=identity,folder=relative,offset=end,size=size,added=True,toc_flags=flags,sha256=spec.get('source_sha256',''))
            if 'template_hash' in spec:entry['template_hash']=spec['template_hash']
            result['entries'].append(entry);end+=(size+2047)&~2047;occupied.add(identity);folders.add(relative)
    return result


class SourceReader:
    def __init__(self,root,manifest=None):
        self.root=Path(root).resolve();self.assets=self.root/'assets'
        self.manifest=augment_manifest(self.root,manifest or json.loads((self.root/'assets.json').read_text()))
        if self.manifest.get('platform')!='xbox360' or self.manifest.get('version')!=1:raise ValueError('Xbox assets version mismatch')
        self.entries={e['hash']:e for e in self.manifest['entries']};self.layouts={}
    def path(self,relative):
        path=(self.root/relative).resolve()
        if not path.is_relative_to(self.assets):raise ValueError('Edit path escapes assets')
        return path
    def layout(self,entry):
        if entry['hash'] not in self.layouts:self.layouts[entry['hash']]=json.loads(self.path(entry['folder']+'/asset.json').read_text())
        return self.layouts[entry['hash']]
    def blocks(self,source):
        entry=self.entries[int(source['bank'])];layout=self.layout(entry);index=int(source['record'])
        if not 0<=index<100000:raise ValueError('Resource index exceeds limit')
        if 'paired_resources' in layout:
            r=next(r for r in layout['paired_resources'] if r['index']==index);kind=r['type'];blocks=[]
            for c in r['component_files']:
                data=self.path(c['folder']+'/'+c['path']).read_bytes() if c['path'] else b''
                if len(data)!=c['size']:raise ValueError('Loose paired component extent changed')
                blocks.append(data)
        elif 'blocks' in layout:
            r=next(r for r in layout['records'] if r['index']==index);blocks=[]
            for j,start in enumerate(r['offsets']):
                if start==0xffffffff:continue
                c=next(c for c in layout['blocks'][j]['components'] if c['start']==start)
                blocks.append(self.path(entry['folder']+'/'+c['path']).read_bytes())
            kind=r['type']
        else:
            head=self.path(entry['folder']+'/payload.dat').read_bytes();u=lambda off:struct.unpack_from('>I',head,off)[0]
            if head[:4]!=bytes.fromhex('f0985030') or index>=u(24):raise ValueError('Unsupported paired resource')
            field=36;target=field+u(field)-1;end=target
            while head[end:end+2]!=b'\0\0':
                end+=2
                if end>len(head)-2:raise ValueError('Unterminated paired bank name')
            name=head[target:end].decode('utf-16-be');paired=self.entries[zlib.crc32(name.upper().encode('ascii'))&0xffffffff]
            field=32;table=field+u(field)-1;field=table+index*4;desc=field+u(field)-1
            recfield=0x68+index*4;record=recfield+u(recfield)-1;kind=u(record+4)
            blocks=[]
            with self.path(paired['folder']+'/payload.dat').open('rb') as data:
                length=data.seek(0,2)
                for offset,size in [(u(desc),u(desc+4)),(u(desc+8),u(desc+12))]:
                    if offset+size>length:raise ValueError('Paired data extent exceeds source')
                    data.seek(offset);blocks.append(decode_component(data.read(size)))
        if 'stream' in source:
            if kind!=0x61df2234:raise ValueError('Not an Xbox stream table')
            b=blocks[0];u=lambda off:struct.unpack_from('>I',b,off)[0]
            end=0
            while b[end:end+2]!=b'\0\0' and end<64:end+=2
            name=b[:end].decode('utf-16-be');paired=self.entries[zlib.crc32(name.upper().encode('ascii'))&0xffffffff]
            stream=int(source['stream']);count,rate,fmt=u(64),u(76),u(84)
            if not 0<=stream<count or fmt not in (2,5):raise ValueError('Unsupported Xbox stream slot')
            start,end=u(92+stream*8),u(100+stream*8);seconds=struct.unpack_from('>f',b,96+stream*8)[0]
            with self.path(paired['folder']+'/payload.dat').open('rb') as data:
                data.seek(0,2)
                if not 0<=start<end<=data.tell():raise ValueError('Stream data exceeds bank')
                data.seek(start);encoded=data.read(end-start)
            blocks=[struct.pack('>11I',1,5,fmt,round(seconds*rate),rate,0,len(encoded),0,32,0,0),encoded];kind=0x1aedda1f
        if 'texture' in source:
            if kind!=0xe26c9b5d or len(blocks)!=2:raise ValueError('Not a split Xbox scene texture')
            cpu,gpu=blocks;u=lambda off:struct.unpack_from('>I',cpu,off)[0];slot=int(source['texture']);count=u(0x20);table=0x24+u(0x24)-1
            if not 0<=slot<count or table+count*224>len(cpu):raise ValueError('Scene texture exceeds descriptor table')
            blocks=[cpu[table+slot*224:table+(slot+1)*224],gpu];kind=0x5c369069
        return kind,blocks
    def records(self,entry):
        layout=self.layout(entry)
        if 'paired_resources' in layout:return layout['paired_resources']
        if 'loose_segments' in layout:return []
        if 'blocks' in layout:return layout['records']
        path=self.path(entry['folder']+'/payload.dat')
        with path.open('rb') as stream:
            if stream.read(4)!=bytes.fromhex('f0985030'):return []
        data=path.read_bytes();u=lambda offset:struct.unpack_from('>I',data,offset)[0];count=u(24)
        if count>100000 or 0x68+count*4>len(data):raise ValueError('Invalid paired resource table')
        result=[]
        for i in range(count):
            field=0x68+i*4;record=field+u(field)-1
            if record<0 or record+12>len(data):raise ValueError('Invalid paired record')
            result.append(dict(index=i,id=u(record),type=u(record+4),folder=f'_resources/{i:04d}_{u(record):08x}'))
        return result
    def discover_edits(self):
        edits=[]
        for entry in self.entries.values():
            for record in self.records(entry):
                folder=self.path(entry['folder']+'/'+record['folder']);source=dict(bank=entry['hash'],record=record['index']);kind=record['type']
                def add(path,kind,reference):edits.append(dict(file=path.relative_to(self.root).as_posix(),kind=kind,source=reference))
                if kind in (0x5c369069,0x5c36fb69) and (folder/'texture.dds').is_file():add(folder/'texture.dds','dds',source)
                elif kind==0xe26c9b5d:
                    for path in folder.glob('texture_*.dds'):
                        match=re.fullmatch(r'texture_([0-9]{4})\.dds',path.name,re.I)
                        if match:add(path,'dds',dict(source,texture=int(match[1])))
                elif kind==0x1aedda1f and (folder/'audio.wav').is_file():add(folder/'audio.wav','pcm',source)
                elif kind==0x61df2234:
                    for path in (folder/'audio').glob('track_*/audio.wav'):
                        match=re.fullmatch(r'track_([0-9]{5})',path.parent.name)
                        if match:add(path,'pcm',dict(source,stream=int(match[1])))
        return edits
    def native_edits(self,texture_exporter,skip_paths=()):
        marker=self.root/'asset_edits.json'
        registry=json.loads(marker.read_text()) if marker.exists() else dict(version=1,platform='xbox360',edits=[])
        if registry.get('version')!=1 or registry.get('platform')!='xbox360':raise ValueError('Unsupported asset edits registry')
        edits=list(registry.get('edits',[]))
        if self.manifest.get('storage')=='loose-resources':edits.extend(self.discover_edits())
        dds=[];pcm=[];seen={str(path).casefold() for path in skip_paths}
        for edit in edits:
            if edit['file'].casefold() in seen:continue
            seen.add(edit['file'].casefold())
            kind,blocks=self.blocks(edit['source']);path=self.path(edit['file']);relative=path.relative_to(self.root).as_posix()
            if edit['kind']=='dds':
                if kind not in (0x5c369069,0x5c36fb69):raise ValueError('DDS target is not a texture')
                original=texture_exporter(blocks[0],blocks[1] if len(blocks)>1 else None)
                dds.append(dict(original=original,data=path.read_bytes(),path=relative))
            elif edit['kind']=='pcm':
                if kind!=0x1aedda1f or len(blocks)!=2 or len(blocks[0])!=44:raise ValueError('PCM target is not Xbox audio')
                version,codec,fmt,samples,rate,flags,size,*unknown=struct.unpack('>11I',blocks[0])
                if version!=1 or codec!=5 or fmt not in (2,5) or not 0<size<=len(blocks[1]) or size%2048:raise ValueError('Unsupported Xbox audio source')
                channels=1 if fmt==2 else 2
                with wave.open(str(path),'rb') as w:
                    if w.getcomptype()!='NONE' or w.getsampwidth()!=2 or (w.getnchannels(),w.getframerate(),w.getnframes())!=(channels,rate,samples):raise ValueError('PCM WAV must retain original channels, rate and sample count')
                prefix=min(size,16384)
                pcm.append(dict(first_hash=fnv(blocks[1][:2048]),prefix_length=prefix,prefix_hash=fnv(blocks[1][:prefix]),channels=channels,rate=rate,samples=samples,path=relative))
            else:raise ValueError('Unsupported native edit kind')
        return dds,pcm
