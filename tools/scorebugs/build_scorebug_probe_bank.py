"""Build an Xbox gamedata IFF with two scorebug aliases for hook research."""
import argparse
import hashlib
import json
import struct
import zlib
from pathlib import Path

SCNE = 0xE26C9B5D
ALIASES = ('scorebug_reborn_espn', 'scorebug_reborn_usa')
COMPONENTS = ('scene.dat', 'scene_gpu.dat')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def build(stock, variants):
    from loose_assets import iff_layout

    layout = json.loads((stock/'asset.json').read_bytes())
    original = (stock/'archive_header.dat').read_bytes()
    table = 27+struct.unpack_from('>I', original, 28)[0]
    count = struct.unpack_from('>I', original, 24)[0]
    if table != 96 or count != len(layout['records']) or len(layout['blocks']) != 2:
        raise ValueError('Unsupported Xbox gamedata header')
    rows = []
    cursor = table+count*4
    for i, record in enumerate(layout['records']):
        field = table+i*4
        start = field+struct.unpack_from('>I', original, field)[0]-1
        length = 12+4*len(record['offsets'])
        raw = original[start:start+length]
        if start != cursor or struct.unpack_from('>III', raw) != (record['id'], record['type'], len(record['offsets'])):
            raise ValueError('Source record table is not the expected contiguous format')
        rows.append((record['id'], raw))
        cursor += length
    if cursor != len(original):
        raise ValueError('Unrecognized header suffix')
    if any(zlib.crc32(alias.encode()) in {key for key,_ in rows} for alias in ALIASES):
        raise ValueError('Alias already exists in the stock bank')

    blocks, baselines, starts = [], [], [[], []]
    for i, spec in enumerate(layout['blocks']):
        payload = bytearray()
        for component in spec['components']:
            data = (stock/component['path']).read_bytes()
            if component['start'] != len(payload) or len(data) != component['end']-component['start'] or digest(data) != component['sha256']:
                raise ValueError('Source component layout or hash differs')
            payload.extend(data)
        if len(payload) != spec['size'] or len(payload) != spec['logical']:
            raise ValueError('Source block is not a full uncompressed block')
        baselines.append(bytes(payload))
        for variant in variants:
            payload.extend(bytes((-len(payload))%4096))
            starts[i].append(len(payload))
            scene = (variant/COMPONENTS[i]).read_bytes()
            if (i == 0 and not 46336 <= len(scene) <= 65536) or (i == 1 and len(scene)!=299008):
                raise ValueError('Unexpected converted Xbox scene length')
            payload.extend(scene)
        blocks.append(payload)

    header = bytearray(original[:table])
    rows.extend((zlib.crc32(alias.encode()), struct.pack('>5I', zlib.crc32(alias.encode()),
                 SCNE, 2, starts[0][i], starts[1][i])) for i,alias in enumerate(ALIASES))
    rows.sort(key=lambda pair:pair[0])  # Python sort preserves original order for tied IDs.
    header.extend(bytes(4*len(rows)))
    for i, (_, row) in enumerate(rows):
        field = table+i*4
        struct.pack_into('>I', header, field, len(header)-field+1)
        header.extend(row)
    block_start = len(header)
    struct.pack_into('>II', header, 4, block_start, block_start+sum(map(len,blocks)))
    struct.pack_into('>I', header, 24, len(rows))
    for i, payload in enumerate(blocks):
        struct.pack_into('>I', header, 32+i*32+12, len(payload))
        struct.pack_into('>II', header, 32+i*32+20, block_start, len(payload))
        block_start += len(payload)
    suffix = (stock/'tail.dat').read_bytes()
    result = bytes(header)+b''.join(blocks)+suffix
    parsed = iff_layout(result)
    existing = [r for r in parsed['records'] if r['id'] not in {zlib.crc32(a.encode()) for a in ALIASES}]
    assert [{k:v for k,v in r.items() if k!='index'} for r in existing] == [
        {k:r[k] for k in ('id','type','offsets')} for r in layout['records']]
    for i, spec in enumerate(parsed['blocks']):
        payload = result[spec['start']:spec['start']+spec['size']]
        assert payload.startswith(baselines[i])
        for j, variant in enumerate(variants):
            source = (variant/COMPONENTS[i]).read_bytes()
            assert payload[starts[i][j]:starts[i][j]+len(source)] == source
            alias = next(r for r in parsed['records'] if r['id']==zlib.crc32(ALIASES[j].encode()))
            assert alias['type']==SCNE and alias['offsets'][i]==starts[i][j]
    assert result.endswith(suffix)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('stock', type=Path)
    p.add_argument('espn', type=Path)
    p.add_argument('usa', type=Path)
    p.add_argument('output', type=Path)
    args=p.parse_args()
    data=build(args.stock,(args.espn,args.usa))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('xb') as output:
        output.write(data)
    print(json.dumps({'file':str(args.output),'sha256':digest(data),
                      'record_ids':{a:f'{zlib.crc32(a.encode()):08x}' for a in ALIASES}}))


if __name__=='__main__':
    main()
