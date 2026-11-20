"""Apply the broadcast-reference logo layout to converted Xbox scenes."""
import argparse
import json
import math
import shutil
import struct
from pathlib import Path
from scene_binary import R, U, meshes, require


def refine(source, output):
    require(not output.exists(), 'Output already exists')
    cpu = bytearray((source / 'scene.dat').read_bytes())
    gpu = bytearray((source / 'scene_gpu.dat').read_bytes())
    changes = []
    arrow = False
    for mesh in meshes(cpu):
        if mesh['name'] not in ('logo1', 'logo2', 'g_2K_circle_logo'):
            continue
        start, stride, length = mesh['streams'][0]
        require(mesh['count'] == 4 and stride == 36, 'Unexpected logo quad')
        points = [struct.unpack_from('>3f', gpu, at)
                  for at in range(start, start + length, stride)]
        if mesh['name'] == 'g_2K_circle_logo':
            require(all(struct.unpack_from('>f', gpu, at+28)[0] == 0
                        for at in range(start, start+length, stride)),
                    'The reserved circle mesh is visible in this source')
            # Reuse the hidden four-vertex strip. Its second triangle is
            # degenerate, leaving a white possession-arrow triangle.
            vertices = [(4., -207., 6.), (4., -201., 6.),
                        (-4., -204., 6.), (-4., -204., 6.)]
            for at, point in zip(range(start, start+length, stride), vertices):
                struct.pack_into('>3f2e4f', gpu, at, *point, .5, .5, 1., 1., 1., 1.)
            center = struct.unpack_from('>3f', cpu, mesh['part']+48)
            struct.pack_into('>f', cpu, mesh['part']+16,
                             max(math.dist(center, point) for point in vertices)+66.)
            arrow = True
            continue
        center_x = sum(p[0] for p in points) / 4
        # A square preserves the original team artwork's proportions.
        center_y = -189.5
        half = 20.0
        for at, point in zip(range(start, start + length, stride), points):
            x = center_x + (half if point[0] > center_x else -half)
            old_center_y = sum(p[1] for p in points) / 4
            y = center_y + (half if point[1] > old_center_y else -half)
            struct.pack_into('>3f', gpu, at, x, y, point[2])
        part = mesh['part']
        # Expand the bounding sphere around the existing authored center.
        # Keep the adjacent vertex count, transform and rotation intact.
        center = struct.unpack_from('>3f', cpu, part+48)
        updated = [struct.unpack_from('>3f', gpu, at)
                   for at in range(start, start+length, stride)]
        radius = max(math.dist(center, point) for point in updated)
        struct.pack_into('>f', cpu, part+16, radius)
        changes.append(dict(mesh=mesh['name'], center=[center_x, center_y], size=[40, 40]))
    require(len(changes) == 2, 'Both team logos are required')
    require(arrow, 'The reserved possession-arrow mesh is required')
    output.mkdir(parents=True)
    (output/'scene.dat').write_bytes(cpu)
    (output/'scene_gpu.dat').write_bytes(gpu)
    shutil.copyfile(source/'port-audit.json', output/'source-port-audit.json')
    report = {'logos': changes, 'possession_mesh': 'g_2K_circle_logo',
              'possession_anchor': [0, -204], 'possession_pose': 1}
    (output/'layout-changes.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({'output': str(output), **report}))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source', type=Path)
    p.add_argument('output', type=Path)
    a = p.parse_args()
    refine(a.source, a.output)
