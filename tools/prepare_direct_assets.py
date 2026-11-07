"""Runtime startup metadata for direct loose-resource loading, without repacking."""
import json
from pathlib import Path
from direct_folder import DirectFolder,publish


def prepare_direct(root):
    # Shared validation helpers do not assemble asset binaries in this path.
    from loose_assets import FolderSnapshot,digest,fnv64,validate_dds,write_map
    from xbox_asset_edits import augment_manifest,SourceReader
    from xbox_texture import export_dds,describe,FORMATS
    root=Path(root).resolve();snapshot=FolderSnapshot(root);folder=DirectFolder(root);manifest=augment_manifest(root,folder.manifest)
    catalog=[];identities={};stamps={};known_paths=set();reader=SourceReader(root,folder.manifest)
    state=root/'_runtime/validation.json'
    try:previous=json.loads(state.read_text())
    except (ValueError,OSError):previous={}
    for entry in manifest['entries']:
        base=snapshot.directory(entry['folder']);layout=reader.layout(entry)
        for texture in layout.get('textures',[]):
            path,stat=snapshot.file(base/texture['path']);relative=path.relative_to(root).as_posix();signature=[stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns];old=previous.get(relative,{})
            if old.get('stat')==signature:checksum=old['sha256']
            else:
                payload=path.read_bytes();checksum=digest(payload)
            stamps[relative]=dict(stat=signature,sha256=checksum);info=texture['descriptor'];key=(info['width'],info['height'],info['format'],texture['identity'])
            known_paths.add(relative)
            if checksum!=texture['sha256']:
                index=texture.get('record')
                if index is None:
                    matches=[r for r in layout['records'] if texture['path']==r['folder']+'/texture.dds']
                    if len(matches)!=1:raise ValueError('Ambiguous DDS resource folder')
                    index=matches[0]['index']
                kind,blocks=reader.blocks(dict(bank=entry['hash'],record=index));original=export_dds(blocks[0],blocks[1] if len(blocks)>1 else None);info=describe(blocks[0],blocks[1] if len(blocks)>1 else None)
                validate_dds(path.read_bytes(),info);key=(info['width'],info['height'],info['format'],fnv64(original[128:]))
            if key in identities and identities[key]!=checksum:raise ValueError('Conflicting native DDS identities')
            if key not in identities and checksum!=texture['sha256']:catalog.append('\t'.join(map(str,[*key,relative])))
            identities[key]=checksum
    extras,pcm=reader.native_edits(export_dds,skip_paths=known_paths);reverse={code:fmt for fmt,(code,bpp) in FORMATS.items()}
    for extra in extras:
        import struct
        original=extra['original'];height,width=struct.unpack_from('<II',original,12);fmt=reverse[original[84:88]];validate_dds(extra['data'],dict(width=width,height=height,format=fmt))
        key=(width,height,fmt,fnv64(original[128:]));checksum=digest(extra['data'])
        if key in identities and identities[key]!=checksum:raise ValueError('Conflicting native DDS identities')
        if key not in identities and extra['data']!=original:catalog.append('\t'.join(map(str,[*key,extra['path']])))
        identities[key]=checksum
    pcm_rows=[];seen={}
    for clip in pcm:
        key=(clip['first_hash'],clip['prefix_length'],clip['prefix_hash'],clip['channels']);checksum=digest((root/clip['path']).read_bytes())
        if key in seen and seen[key]!=checksum:raise ValueError('Conflicting native WAV identities')
        if key not in seen:pcm_rows.append('\t'.join(map(str,[*key,clip['rate'],clip['samples'],clip['path']])))
        seen[key]=checksum
    plan=folder.plan(manifest)
    # Metadata is published only after every resource and native binding validates.
    publish(root/'native_dds.index',('CH2K8_DDS_V1\n'+'\n'.join(catalog)+'\n').encode())
    publish(root/'native_audio.index',('CH2K8_PCM_V1\n'+'\n'.join(pcm_rows)+'\n').encode())
    write_map(root,plan)
    publish(state,(json.dumps(stamps,indent=2)+'\n').encode())
    print(f'Direct loose resources ready: {len(manifest["entries"])} banks, {len(plan["parts"])} virtual loader parts, {len(catalog)} native DDS bindings; no packed asset blocks or asset-cache binaries used.')
    return plan

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('root',type=Path);args=parser.parse_args();prepare_direct(args.root)
