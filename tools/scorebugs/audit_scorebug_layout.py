"""Verify the broadcast layout changes against the audited source conversion."""
import argparse
import json
import math
import struct
from pathlib import Path
from scene_binary import meshes, require


def audit(source, output):
    original_cpu = (source/'scene.dat').read_bytes()
    original_gpu = (source/'scene_gpu.dat').read_bytes()
    cpu = (output/'scene.dat').read_bytes()
    gpu = (output/'scene_gpu.dat').read_bytes()
    require(len(cpu) == len(original_cpu) and len(gpu) == len(original_gpu),
            'Component sizes changed')
    before = {mesh['name']: mesh for mesh in meshes(original_cpu)}
    after = {mesh['name']: mesh for mesh in meshes(cpu)}
    require(before.keys() == after.keys(), 'Mesh identities changed')
    cpu_ranges, gpu_ranges = [], []
    changed = {'logo1', 'logo2', 'g_2K_circle_logo'}
    for name in changed:
        mesh = after[name]
        require(mesh == before[name], 'A mesh descriptor changed')
        part = mesh['part']
        cpu_ranges.append((part+16, part+20))
        start, stride, length = mesh['streams'][0]
        points = []
        for at in range(start, start+length, stride):
            points.append(struct.unpack_from('>3f', gpu, at))
            gpu_ranges.append((at, at+(32 if name == 'g_2K_circle_logo' else 12)))
            require(gpu[at+32:at+36] == original_gpu[at+32:at+36],
                    'Packed bone lanes changed')
        center = struct.unpack_from('>3f', cpu, part+48)
        radius = struct.unpack_from('>f', cpu, part+16)[0]
        require(all(math.dist(center, point) <= radius+1e-4 for point in points),
                'Geometry exceeds the bounding sphere')
        if name != 'g_2K_circle_logo':
            for axis in (0, 1):
                require(abs(max(p[axis] for p in points)-min(p[axis] for p in points)-40) < 1e-4,
                        'A logo is not square at the requested size')
        else:
            require(points[2] == points[3], 'Arrow strip has an extra visible triangle')
            for at in range(start, start+length, stride):
                require(struct.unpack_from('>2e4f', gpu, at+12) == (.5, .5, 1., 1., 1., 1.),
                        'Arrow UV or vertex color differs')
    for original, current, allowed, label in ((original_cpu, cpu, cpu_ranges, 'CPU'),
                                             (original_gpu, gpu, gpu_ranges, 'GPU')):
        require(all(a == b or any(low <= offset < high for low, high in allowed)
                    for offset, (a, b) in enumerate(zip(original, current))),
                'Unexpected '+label+' edit')
    report = dict(meshes=len(after), resized_logos=2, possession_triangles=1,
                  unaffected_cpu_and_gpu_bytes_exact=True)
    (output/'layout-audit.json').write_text(json.dumps(report, indent=2)+'\n')
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source', type=Path)
    p.add_argument('output', type=Path)
    a = p.parse_args()
    print(json.dumps(audit(a.source, a.output)))
