"""Convert a PS3 bottom-bar scorebug into two Xbox scene components."""
import argparse
import json
import math
import struct
import zipfile
from pathlib import Path

from scene_binary import R, U, meshes, require, take

PS3_ATTRIBUTES = ('2000000002030000', '200c000003020800',
                  '2010000002040300', '2020000007040700')
XBOX_ATTRIBUTES = ('20000000002a23b9', '200c0000002c235f',
                   '20100000001a23a6', '20200000001a2286')


def convert(xbox_cpu, xbox_gpu, ps3_cpu, ps3_gpu):
    target_meshes = meshes(xbox_cpu)
    source_meshes = {m['name']: m for m in meshes(ps3_cpu, ps3=True)}
    require(len(target_meshes) == len(source_meshes) == 23 and
            {m['name'] for m in target_meshes} == set(source_meshes), 'Unexpected scorebug mesh set')
    cpu, gpu = bytearray(xbox_cpu), bytearray(xbox_gpu)
    cpu_ranges, gpu_ranges = [], []

    def patch(buffer, offset, data, edits):
        take(buffer, offset, len(data))
        require(all(offset + len(data) <= a or offset >= b for a,b in edits),
                'Overlapping scorebug conversion ranges')
        buffer[offset:offset+len(data)] = data
        edits.append((offset, offset+len(data)))

    # The PS3 cone index buffer has two extra indices. Move it into the
    # original zero padding without growing either Xbox component.
    geometry_end = max(offset+length for m in target_meshes for offset, _, length in m['streams'])
    tail = (geometry_end+15)&~15
    require(not any(gpu[tail:]), 'Xbox scorebug padding contains data')
    for target in target_meshes:
        name = target['name']
        source = source_meshes[name]
        require(target['count'] == source['count'], 'Vertex count differs: '+name)
        require(tuple(v[2].hex() for v in source['attrs'].values()) == PS3_ATTRIBUTES and
                tuple(v[2].hex() for v in target['attrs'].values()) == XBOX_ATTRIBUTES,
                'Unexpected scorebug vertex declaration: '+name)
        require(len(source['streams']) == len(target['streams']) == 1, 'Expected one vertex stream')
        src, ss, n = source['streams'][0]
        dst, ds, m = target['streams'][0]
        require(ss == ds == 36 and n == m, 'Unexpected scorebug vertex stride')
        vertices = bytearray(take(ps3_gpu, src, n))
        for at in range(0, n, 36):
            require(all(math.isfinite(v) for v in struct.unpack_from('>3f2e4f', vertices, at)),
                    'Nonfinite PS3 position, UV, or color')
            # PS3 stores the packed color byte lanes in the reverse order.
            vertices[at+32:at+36] = vertices[at+32:at+36][::-1]
        patch(gpu, dst, vertices, gpu_ranges)
        sp, xp = source['part'], target['part']
        # Bounds and the authored local transform follow the moved vertices.
        # Keep the platform-specific flags, stream declarations and pointers.
        patch(cpu, xp+0x10, take(ps3_cpu, sp+0x10, 0x50), cpu_ranges)
        bone_count = U(ps3_cpu,sp+0x60)
        require(bone_count == U(xbox_cpu,xp+0x60), 'Bone count differs: '+name)
        source_bones, target_bones = R(ps3_cpu,sp+0x64), R(xbox_cpu,xp+0x64)
        for i in range(bone_count):
            src_bone, dst_bone = source_bones+i*48, target_bones+i*48
            require(take(ps3_cpu,src_bone+36,12) == take(xbox_cpu,dst_bone+36,12),
                    'Bone binding differs: '+name)
            patch(cpu,dst_bone,take(ps3_cpu,src_bone,32),cpu_ranges)
        source_count, target_count = U(ps3_cpu,sp+0xa8), U(xbox_cpu,xp+0xa8)
        index = take(ps3_gpu, U(ps3_cpu,sp+0xac)-1, source_count*2)
        require(all(v == 65535 or v < source['count'] for (v,) in struct.iter_unpack('>H', index)),
                'PS3 index exceeds vertex count')
        index_dst = U(xbox_cpu,xp+0xac)-1
        if source_count != target_count:
            require(name == 'pCone1' and source_count == 227 and target_count == 225,
                    'Unexpected index count change')
            index_dst = tail
            patch(cpu, xp+0xa8, struct.pack('>II', source_count, index_dst+1), cpu_ranges)
        patch(gpu, index_dst, index, gpu_ranges)
        run_count = U(ps3_cpu,sp+0x7c)
        require(run_count == U(xbox_cpu,xp+0x7c), 'Unexpected draw run count')
        sr, xr = R(ps3_cpu,sp+0x80), R(xbox_cpu,xp+0x80)
        for i in range(run_count):
            run = take(ps3_cpu, sr+i*48, 48)
            mode, first, count, _ = struct.unpack_from('>4I', run)
            require(mode == 6 and first+count <= source_count,
                    'Unexpected PS3 draw run')
            require(U(ps3_cpu,sr+i*48+32) < U(ps3_cpu,0x30),
                    'Draw references an unknown material')
            patch(cpu, xr+i*48, run, cpu_ranges)

    def instance_table(data):
        count, tab = U(data,0x3c), R(data,0x40)
        require(count == 23, 'Unexpected instance count')
        rows = {U(data,tab+i*144+68):tab+i*144 for i in range(count)}
        require(len(rows) == count, 'Duplicate scorebug instance ID')
        return rows

    si, xi = instance_table(ps3_cpu), instance_table(xbox_cpu)
    require(si.keys() == xi.keys(), 'Scorebug instance IDs differ')
    for key, dst in xi.items():
        matrix = take(ps3_cpu, si[key], 64)
        values = struct.unpack('>16f',matrix)
        require(all(math.isfinite(v) for v in values) and values[15] == 1, 'Invalid PS3 transform')
        patch(cpu, dst, matrix, cpu_ranges)
        source_model = next(m for m in source_meshes.values() if U(ps3_cpu,m['part']+4)==key)
        count = U(ps3_cpu,source_model['part']+0x60)
        source_pose, target_pose = R(ps3_cpu,si[key]+0x74), R(xbox_cpu,dst+0x74)
        poses = take(ps3_cpu,source_pose,count*64)
        require(all(math.isfinite(v) for v in struct.unpack('>'+str(count*16)+'f',poses)),
                'Invalid bone pose')
        patch(cpu,target_pose,poses,cpu_ranges)

    def text_rows(data):
        table = R(data, 0x50)
        result = {}
        for i in range(U(data, 0x4c)):
            row = table+i*144
            from scene_binary import string
            name = string(data, R(data, row+64))
            require(name not in result, 'Duplicate scorebug text binding')
            result[name] = row
        return result

    source_text, target_text = text_rows(ps3_cpu), text_rows(xbox_cpu)
    require(source_text.keys() == target_text.keys(), 'Scorebug text bindings differ')
    for name, dst in target_text.items():
        src = source_text[name]
        patch(cpu, dst, take(ps3_cpu, src, 64), cpu_ranges)
        patch(cpu, dst+96, take(ps3_cpu, src+96, 12), cpu_ranges)
        source_style, target_style = R(ps3_cpu,src+80), R(xbox_cpu,dst+80)
        require(U(ps3_cpu,source_style) == U(xbox_cpu,target_style), 'Text style count differs')
        for i in range(U(ps3_cpu,source_style)):
            old, new = target_style+16+i*32, source_style+16+i*32
            kind = U(ps3_cpu,new+16)
            require(take(ps3_cpu,new+16,16) == take(xbox_cpu,old+16,16),
                    'Text style property layout differs: '+name)
            if kind == 3:
                # Repoint strings to an appended, bounded UTF-16 pool.
                # Literal names are retained; font aliases are resolved on Xbox.
                value = U(ps3_cpu,new)
                if not value:
                    patch(cpu,old,bytes(16),cpu_ranges)
                    continue
                at = R(ps3_cpu,new)
                end = at
                while take(ps3_cpu,end,2) != bytes(2):
                    end += 2
                    require(end-at <= 2048, 'Unterminated scorebug style string')
                literal = take(ps3_cpu,at,end-at+2)
                if literal != take(xbox_cpu,R(xbox_cpu,old),len(literal)):
                    cpu.extend(bytes((-len(cpu))%16))
                    address = len(cpu)
                    cpu.extend(literal)
                    patch(cpu,old,struct.pack('>I',address-old+1)+take(ps3_cpu,new+4,12),cpu_ranges)
            else:
                require(kind in (0,1,2), 'Unsupported scorebug text property type')
                patch(cpu,old,take(ps3_cpu,new,16),cpu_ranges)

    # Match each material by hash, then translate parameter offsets through
    # the PS3 and Xbox shader declarations. The GPU descriptors stay native.
    def material_rows(data):
        table = R(data,0x38)
        return {U(data,table+i*40): table+i*40 for i in range(U(data,0x30))}

    def shader(data, material):
        table = R(data,0x2c)
        matches = [table+i*48 for i in range(U(data,0x28))
                   if U(data,table+i*48) == U(data,material+8)]
        require(len(matches) == 1, 'Missing material shader')
        entry = matches[0]
        uniform_count, sampler_count = U(data,entry+8)>>16, U(data,entry+8)&65535
        uniforms = R(data,entry+24)
        samplers = R(data,entry+28)
        return ({U(data,uniforms+i*44): uniforms+i*44 for i in range(uniform_count)},
                {U(data,samplers+i*36): samplers+i*36 for i in range(sampler_count)},
                U(data,entry+12)&65535)

    source_materials, target_materials = material_rows(ps3_cpu), material_rows(xbox_cpu)
    require(source_materials.keys() == target_materials.keys(), 'Material identities differ')
    for key, dst in target_materials.items():
        src = source_materials[key]
        source_uniforms, source_samplers, source_length = shader(ps3_cpu,src)
        target_uniforms, target_samplers, target_length = shader(xbox_cpu,dst)
        require(source_uniforms.keys() == target_uniforms.keys() and
                source_samplers.keys() == target_samplers.keys(), 'Shader parameter identities differ')
        source_params, target_params = R(ps3_cpu,src+32), R(xbox_cpu,dst+32)
        for identity, uniform in source_uniforms.items():
            source_offset = struct.unpack_from('>H',ps3_cpu,uniform+20)[0]
            target_offset = struct.unpack_from('>H',xbox_cpu,target_uniforms[identity]+20)[0]
            require(source_offset+16<=source_length and target_offset+16<=target_length,
                    'Uniform parameter exceeds material')
            patch(cpu,target_params+target_offset,take(ps3_cpu,source_params+source_offset,16),cpu_ranges)
        for identity, sampler in source_samplers.items():
            source_offset = struct.unpack_from('>H',ps3_cpu,sampler+16)[0]+12
            target_offset = struct.unpack_from('>H',xbox_cpu,target_samplers[identity]+16)[0]+12
            require(source_offset+4<=source_length and target_offset+4<=target_length,
                    'Sampler parameter exceeds material')
            patch(cpu,target_params+target_offset,take(ps3_cpu,source_params+source_offset,4),cpu_ranges)

    cpu.extend(bytes((-len(cpu))%16))
    require(len(gpu) == len(xbox_gpu), 'Xbox GPU component length changed')
    require(all(a == b or any(lo<=i<hi for lo,hi in cpu_ranges)
                for i,(a,b) in enumerate(zip(cpu,xbox_cpu))), 'Unexpected CPU edit')
    require(len(meshes(cpu)) == 23, 'Converted Xbox geometry failed to reparse')
    return bytes(cpu), bytes(gpu)



def bake_artwork(cpu, gpu, artwork):
    """Pack converted DDS base levels into their native Xbox texture spans."""
    from choops_recomp import dds, raw_texture

    names = ('polysurface16_diffuse_1c0a45df.dds', 'diffuse_ecd26057.dds',
             'diffuse_e2a8738a.dds', 'diffuse_4446ec65.dds', 'diffuse_149c79a7.dds')
    data = bytearray(gpu)
    table = R(cpu, 0x24)
    require(U(cpu, 0x20) == 6, 'Unexpected Xbox scorebug texture count')
    for i, name in enumerate(names):
        descriptor = take(cpu, table+i*224, 224)
        original = dds.xbox_dds(descriptor, gpu)
        path = artwork/name
        if not path.is_file():
            # Studio exports only modified slots.
            continue
        replacement = path.read_bytes()
        expected, incoming = dds.info(original), dds.info(replacement)
        require(expected == incoming and original[76:108] == replacement[76:108],
                'Artwork does not match the Xbox DDS descriptor: '+name)
        if 'raw_format' in expected:
            layout = raw_texture.describe(descriptor, gpu)
            for offset, value in zip(raw_texture.addresses(layout),
                                     replacement[expected['data_offset']:], strict=True):
                data[layout['start']+offset] = value
        else:
            a, b = struct.unpack_from('>II', descriptor, 0x94)
            _, block_size = dds.FORMATS[b&63]
            start, length = U(descriptor,0x6c)-1, U(descriptor,0x70)
            pitch = (a>>22&511)*8
            width, height = expected['width'], expected['height']
            require(not expected.get('direct_component'), 'Unexpected packed scorebug texture')
            swap = (0,1,3,2)[b>>6&3]
            cursor = 128
            for y in range((height+3)//4):
                for x in range((width+3)//4):
                    offset = (dds.tiled_offset(x,y,pitch,block_size.bit_length()-1) if a>>31
                              else (y*pitch+x)*block_size)
                    require(offset+block_size <= length, 'Scorebug texture address exceeds its span')
                    block = take(replacement, cursor, block_size)
                    data[start+offset:start+offset+block_size] = bytes(block[j^swap] for j in range(block_size))
                    cursor += block_size
        require(dds.xbox_dds(descriptor, data)[128:] == replacement[128:],
                'Converted DDS did not reparse to the supplied pixels: '+name)
    return bytes(data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('xbox_scene', type=Path)
    parser.add_argument('archive', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--artwork', type=Path, help='Folder of Xbox DDS overrides exported by Studio')
    args = parser.parse_args()
    with zipfile.ZipFile(args.archive) as z:
        members = [m for m in z.infolist() if Path(m.filename).name == 'scorebug_bottombar.scne']
        require(len(members) == 1 and members[0].file_size <= 1024*1024, 'Missing or oversized scorebug SCNE')
        wrapped = z.read(members[0])
    require(wrapped[:4] == b'2kTl' and len(wrapped) == 20+U(wrapped,12)+U(wrapped,16),
            'Invalid PS3 tool envelope')
    source_cpu = take(wrapped,20,U(wrapped,12))
    source_gpu = take(wrapped,20+len(source_cpu),U(wrapped,16))
    paths = [args.xbox_scene/name for name in ('scene.dat','scene_gpu.dat')]
    cpu, gpu = convert(*(p.read_bytes() for p in paths),source_cpu,source_gpu)
    if args.artwork:
        gpu = bake_artwork(cpu, gpu, args.artwork)
    args.output.mkdir(parents=True,exist_ok=False)
    (args.output/'scene.dat').write_bytes(cpu)
    (args.output/'scene_gpu.dat').write_bytes(gpu)
    print(json.dumps({'output': str(args.output), 'meshes': 23, 'instances': 23,
                      'cpu_bytes':len(cpu), 'gpu_bytes':len(gpu)}))


if __name__ == '__main__':
    main()
