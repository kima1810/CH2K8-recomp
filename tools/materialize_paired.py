"""Split Xbox paired resources into authoritative files without rebuilding banks.

Original payload files remain as migration backups, never as mapping inputs for
converted pairs. Partial overlapping extents are rejected; exact shared extents
retain a single owning file. Unclaimed bytes are preserved individually.
"""
import copy,json,struct,zlib
from pathlib import Path
from direct_folder import contained,publish


def materialize_pair(root,entry,paired):
    from xbox_asset_edits import decode_component
    root=Path(root).resolve();folder=contained(root,entry['folder']);data_folder=contained(root,paired['folder'])
    layout=json.loads((folder/'asset.json').read_text());data_layout=json.loads((data_folder/'asset.json').read_text())
    if layout.get('paired_resources'):return 0
    if data_layout.get('loose_segments') and data_layout.get('paired_owner')!=entry['folder']:raise ValueError('Paired data already belongs to another descriptor bank')
    head=bytearray((folder/'payload.dat').read_bytes());data_path=data_folder/'payload.dat';data_size=data_path.stat().st_size
    if data_size>256*1024*1024:raise ValueError('Paired migration currently limits individual data banks to 256 MiB')
    u=lambda p:struct.unpack_from('>I',head,p)[0]
    if head[:4]!=bytes.fromhex('f0985030'):raise ValueError('Not Xbox paired metadata')
    count=u(24);table=32+u(32)-1
    if count>100000 or 0x68+count*4>len(head) or table<0 or table+count*4>len(head):raise ValueError('Invalid paired table')
    records=[];extents=set();patches=[]
    for i in range(count):
        field=0x68+i*4;rec=field+u(field)-1;field=table+i*4;desc=field+u(field)-1
        if min(rec,desc)<0 or rec+20>len(head) or desc+16>len(head):raise ValueError('Invalid paired descriptor')
        ranges=[(u(desc),u(desc+4)),(u(desc+8),u(desc+12))]
        if any(off+size>data_size for off,size in ranges):raise ValueError('Paired extent exceeds data')
        record=dict(index=i,id=u(rec),type=u(rec+4),offsets=[],folder=f'_resources/{i:04d}_{u(rec):08x}',component_files=[])
        for j,extent in enumerate(ranges):
            extents.add(extent);patches.append((desc+j*8,extent));record['component_files'].append(extent)
        records.append(record)
    ordered=sorted(extents);end=0
    for off,size in ordered:
        if size and off<end:raise ValueError('Partially overlapping paired components are unsupported')
        end=max(end,off+size)
    # Validate/decode everything before publishing folder metadata.
    chunks=[];mapping={};cursor=0;source_cursor=0
    with data_path.open('rb') as stream:
        for off,size in ordered:
            if not size:
                mapping[(off,size)]=(0,0,None);continue
            if off>source_cursor:
                stream.seek(source_cursor);gap=stream.read(off-source_cursor);chunks.append((f'_loose/gap_{source_cursor:08x}.dat',gap))
                cursor+=len(gap)
            stream.seek(off);raw=stream.read(size)
            if len(raw)!=size:raise ValueError('Paired data changed while reading')
            decoded=decode_component(raw);name=f'_loose/component_{off:08x}_{size:08x}.dat'
            mapping[(off,size)]=(cursor,len(decoded),name);chunks.append((name,decoded));cursor+=len(decoded);source_cursor=off+size
        if source_cursor<data_size:
            stream.seek(source_cursor);tail=stream.read();chunks.append((f'_loose/gap_{source_cursor:08x}.dat',tail));cursor+=len(tail)
    for offset,extent in patches:
        start,size,path=mapping[extent];struct.pack_into('>II',head,offset,start,size)
    for record in records:
        record['component_files']=[dict(folder=paired['folder'],path=mapping[e][2],size=mapping[e][1]) for e in record['component_files']]
    segments=[];offset=0
    for path,data in chunks:
        publish(data_folder/path,data);segments.append(dict(offset=offset,size=len(data),path=path));offset+=len(data)
    metadata='_loose/descriptor.header';publish(folder/metadata,head)
    new_data=copy.deepcopy(data_layout);new_data['loose_segments']=segments;new_data['loose_size']=cursor;new_data['paired_owner']=entry['folder']
    new_layout=copy.deepcopy(layout);new_layout['paired_resources']=records;new_layout['loose_segments']=[dict(offset=0,size=len(head),path=metadata)];new_layout['loose_size']=len(head)
    # Owner metadata is the atomic commit point. DirectFolder ignores a data
    # layout until its owner publishes paired_resources. Interrupted conversions
    # therefore retain the old mapping and can be retried from untouched backups.
    publish(data_folder/'asset.json',(json.dumps(new_data,indent=2)+'\n').encode())
    publish(folder/'asset.json',(json.dumps(new_layout,indent=2)+'\n').encode())
    return count


def materialize(root,keep_originals=True):
    root=Path(root).resolve();manifest=json.loads((root/'assets.json').read_text());entries={e['hash']:e for e in manifest['entries']};total=0
    if manifest.get('platform')!='xbox360' or manifest.get('storage')!='loose-resources':raise ValueError('Modern Xbox loose resources required')
    for entry in entries.values():
        folder=contained(root,entry['folder']);layout=json.loads((folder/'asset.json').read_text())
        if 'blocks' in layout or layout.get('loose_segments'):continue
        path=folder/'payload.dat'
        with path.open('rb') as stream:prefix=stream.read(4)
        if prefix!=bytes.fromhex('f0985030'):continue
        head=path.read_bytes();start=36+struct.unpack_from('>I',head,36)[0]-1;end=start
        while end+2<=len(head) and head[end:end+2]!=b'\0\0':end+=2
        if end+2>len(head):raise ValueError('Unterminated paired name')
        name=head[start:end].decode('utf-16-be');identity=zlib.crc32(name.upper().encode('ascii'))&0xffffffff
        total+=materialize_pair(root,entry,entries[identity])
    if not keep_originals:
        # Fresh imports only: remove exact obsolete payload files after all pairs
        # commit. Never remove directories or source-disc data.
        for entry in entries.values():
            folder=contained(root,entry['folder']);layout=json.loads((folder/'asset.json').read_text())
            if 'loose_segments' not in layout:continue
            if 'paired_owner' in layout:
                owner=contained(root,layout['paired_owner'])
                if 'paired_resources' not in json.loads((owner/'asset.json').read_text()):raise ValueError('Incomplete paired owner commit')
            backup=folder/'payload.dat'
            if backup.is_file():backup.unlink()
    return total


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('root',type=Path);args=p.parse_args();print(f'Materialized {materialize(args.root)} paired resources')
