"""Plan direct loose-resource reads; never encode or rebuild asset containers.

Only small compatibility headers/padding are generated for the existing guest
loader. Every resource body is read from its authoritative folder component.
Packed .stored blocks and assembled asset-cache binaries are never consumed.
"""
import hashlib,json,math,struct
from pathlib import Path


def contained(root,relative):
    path=(root/relative).resolve()
    if not path.is_relative_to(root):raise ValueError('Loose resource path escapes installation')
    return path


def publish(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.is_file() and path.read_bytes()==data:return
    temporary=path.with_name(path.name+'.tmp');temporary.write_bytes(data);temporary.replace(path)


def compatibility_metadata(header,entries,part_count,part_size):
    prefix=24+part_count*16
    if len(header)<prefix+len(entries)*16:raise ValueError('Missing loader metadata')
    words=list(struct.unpack_from('>6I',header));flags={str(e['hash']):struct.unpack_from('>I',header,prefix+e['index']*16+8)[0] for e in entries}
    part_flags=[struct.unpack_from('>I',header,24+i*16+4)[0] for i in range(part_count)]
    return dict(version=1,platform='xbox360',header=words,toc_flags=flags,part_flags=part_flags,part_size=part_size)


class DirectFolder:
    def __init__(self,root):
        self.root=Path(root).resolve();self.manifest=json.loads((self.root/'assets.json').read_text(encoding='utf-8'))
        if self.manifest.get('version')!=1 or self.manifest.get('platform')!='xbox360':raise ValueError('Xbox loose assets are required')
        self.metadata=self.root/'_runtime';self.metadata.mkdir(exist_ok=True)
        provenance=self.metadata/'compatibility.json'
        if self.manifest.get('loader_metadata'):self.compatibility=self.manifest['loader_metadata']
        elif provenance.is_file():self.compatibility=json.loads(provenance.read_text())
        else:
            # One-time migration of opaque loader metadata. No asset payloads.
            first=next(s for s in self.manifest['segments'] if s['offset']==0)
            prefix=24+len(self.manifest['parts'])*16;size=prefix+len(self.manifest['entries'])*16
            with contained(self.root,first['path']).open('rb') as stream:header=stream.read(size)
            if len(header)!=size:raise ValueError('Missing legacy loader metadata for migration')
            self.compatibility=compatibility_metadata(header,self.manifest['entries'],len(self.manifest['parts']),self.manifest['parts'][0]['size'])
            publish(provenance,(json.dumps(self.compatibility,indent=2)+'\n').encode())
    def zero(self,size):
        relative=f'_runtime/padding/{size}.pad'
        if size:publish(self.root/relative,bytes(size))
        return dict(size=size,path=relative)
    def bank(self,entry):
        folder=contained(self.root,entry['folder']);layout=json.loads((folder/'asset.json').read_text())
        if folder.parent!=self.root/'assets':raise ValueError('Loose bank lies outside assets')
        committed=True
        if 'paired_owner' in layout:
            owner=contained(self.root,layout['paired_owner'])
            if owner.parent!=self.root/'assets':raise ValueError('Paired owner lies outside assets')
            committed='paired_resources' in json.loads((owner/'asset.json').read_text())
        if 'loose_segments' in layout and committed:
            segments=[];cursor=0
            for segment in layout['loose_segments']:
                source=contained(folder,segment['path']);size=source.stat().st_size
                if segment['offset']!=cursor or size!=segment['size']:raise ValueError('Loose paired component extent changed')
                segments.append(dict(offset=cursor,size=size,path=source.relative_to(self.root).as_posix()));cursor+=size
            if cursor!=layout['loose_size']:raise ValueError('Incomplete paired component mapping')
            return dict(size=cursor,segments=segments)
        if 'blocks' not in layout:
            path=entry['folder']+'/payload.dat';size=contained(self.root,path).stat().st_size
            return dict(size=size,segments=[dict(offset=0,size=size,path=path)] if size else [])
        pieces=sorted(layout['pieces'],key=lambda p:p['offset']);prefix=next(p for p in pieces if p['offset']==0)
        header=bytearray(contained(folder,prefix['path']).read_bytes())
        if len(header)!=prefix['size'] or len(header)<layout['header'] or header[:4]!=bytes.fromhex('ff3bef94'):raise ValueError('Invalid loose bank header metadata')
        if struct.unpack_from('>I',header,16)[0]!=len(layout['blocks']):raise ValueError('Loose block descriptor count mismatch')
        blocks={b['path']:b for b in layout['blocks']};segments=[];cursor=0
        header_path=f'_runtime/headers/{entry["hash"]:08x}.pending'
        for piece in pieces:
            block=blocks.get(piece['path'])
            if block is not None:
                alignment=4096 if block['start']%4096==0 else 16 if block['start']%16==0 else 1
                padding=(-cursor)%alignment
                if padding:segments.append(dict(offset=cursor,**self.zero(padding)));cursor+=padding
                start=cursor;logical=0
                for component in sorted(block['components'],key=lambda c:c['start']):
                    if component['start']!=logical:raise ValueError('Loose components have a gap or overlap')
                    source=contained(folder,component['path']);path=source.relative_to(self.root).as_posix();size=source.stat().st_size;old_size=component['end']-component['start']
                    if size!=old_size:
                        whole_roster=(len(layout['records'])==1 and layout['records'][0]['type']==0xc61649b2 and len(block['components'])==1 and component['start']==0 and component['end']==block['logical'])
                        if not whole_roster or size<old_size or size%2 or size>64*1024*1024:raise ValueError('Unsupported loose resource resizing')
                    if size:segments.append(dict(offset=cursor,size=size,path=path))
                    cursor+=size;logical=component['end']
                if logical!=block['logical']:raise ValueError('Incomplete loose resource block')
                length=cursor-start
                struct.pack_into('>I',header,32+block['index']*32+12,length)
                struct.pack_into('>II',header,32+block['index']*32+20,start,length)
            else:
                path=header_path if piece['offset']==0 else entry['folder']+'/'+piece['path']
                if piece['offset']!=0 and contained(folder,piece['path']).stat().st_size!=piece['size']:raise ValueError('Loose metadata/padding size changed')
                if piece['size']:segments.append(dict(offset=cursor,size=piece['size'],path=path))
                cursor+=piece['size']
        struct.pack_into('>I',header,8,layout['length']+cursor-entry['size'])
        identity=hashlib.sha256(header).hexdigest();final=f'_runtime/headers/{entry["hash"]:08x}_{identity}.header';publish(self.root/final,header)
        segments[0]['path']=final
        if any(s['path'].endswith('.stored') for s in segments):raise ValueError('Packed blocks must not enter a direct folder view')
        return dict(size=cursor,segments=segments)
    def plan(self,manifest=None):
        manifest=manifest or self.manifest;views=[(entry,self.bank(entry)) for entry in manifest['entries']];part_size=self.compatibility['part_size']
        if part_size%2048 or not part_size:raise ValueError('Invalid virtual loader part size')
        part_count=1
        for _ in range(8):
            header_size=24+part_count*16+len(views)*16;cursor=(header_size+2047)&~2047
            for entry,view in views:cursor=(cursor+view['size']+2047)&~2047
            count=max(1,(cursor+part_size-1)//part_size)
            if count==part_count:break
            part_count=count
        else:raise ValueError('Virtual loader metadata did not converge')
        if part_count>26:raise ValueError('Loose resources exceed the current virtual loader capacity')
        total=cursor;parts=[dict(name='0'+chr(65+i),offset=i*part_size,size=min(part_size,total-i*part_size)) for i in range(part_count)]
        words=list(self.compatibility['header']);words[2]=part_count;words[4]=len(views);header=bytearray(struct.pack('>6I',*words))
        for i,part in enumerate(parts):
            flags=self.compatibility.get('part_flags',[]);flag=flags[i] if i<len(flags) else flags[0] if flags else 0
            header.extend(struct.pack('>II8s',part['size']//2048,flag,part['name'].encode('utf-16-be').ljust(8,b'\0')))
        prefix=len(header);header.extend(bytes(len(views)*16));segments=[dict(offset=0,size=len(header),path='_runtime/pending.header')];cursor=len(header)
        padding=(-cursor)%2048
        if padding:segments.append(dict(offset=cursor,**self.zero(padding)));cursor+=padding
        positions={}
        for entry,view in views:
            positions[entry['hash']]=(cursor,view['size'])
            segments.extend(dict(segment,offset=cursor+segment['offset']) for segment in view['segments']);cursor+=view['size']
            padding=(-cursor)%2048
            if padding:segments.append(dict(offset=cursor,**self.zero(padding)));cursor+=padding
        for i,(entry,view) in enumerate(sorted(views,key=lambda p:p[0]['hash'])):
            position,size=positions[entry['hash']];template=str(entry.get('template_hash',entry['hash']));flag=entry['toc_flags'] if 'toc_flags' in entry else self.compatibility['toc_flags'][template]
            struct.pack_into('>4I',header,prefix+i*16,entry['hash'],position//2048,flag,size)
        identity=hashlib.sha256(header).hexdigest();header_path=f'_runtime/catalog_{identity}.header';publish(self.root/header_path,header);segments[0]['path']=header_path
        if cursor!=total:raise ValueError('Direct resource coverage mismatch')
        return dict(parts=parts,segments=segments,total=total,entries=positions,mode='direct-resources')
