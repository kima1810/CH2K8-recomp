"""Report backend experiments without treating guest submissions as display FPS."""
import argparse
import csv
import json
import statistics
import re
import struct
from datetime import datetime
from pathlib import Path

from summarize_guest_frames import summarize


def read_csv(path):
    if not path.is_file():
        return []
    with path.open(encoding='utf-8-sig') as stream:
        return list(csv.DictReader(stream))


def inspect_native_readback(path):
    """Inspect our top-down BGRA BMPs, ignoring alpha when detecting black."""
    data = path.read_bytes()
    if len(data) < 54 or data[:2] != b'BM':
        return {'file': path.name, 'error': 'Invalid BMP header'}
    offset = struct.unpack_from('<I', data, 10)[0]
    width, height = struct.unpack_from('<ii', data, 18)
    bits = struct.unpack_from('<H', data, 28)[0]
    compression = struct.unpack_from('<I', data, 30)[0]
    if not (0 < width <= 8192 and -8192 <= height < 0 and bits == 32 and compression == 0):
        return {'file': path.name, 'error': 'Unsupported native readback layout'}
    pixels = width * -height
    if offset < 54 or offset+pixels*4 > len(data):
        return {'file': path.name, 'error': 'Truncated native readback'}
    count = sum(bool(data[i] or data[i+1] or data[i+2]) for i in range(offset,offset+pixels*4,4))
    return {'file': path.name, 'width': width, 'height': -height,
            'all_black': count == 0, 'non_black_pixel_fraction': count/pixels}


def summarize_run(root, start=120, end=180):
    root = Path(root)
    metadata = json.loads((root/'run.json').read_text(encoding='utf-8-sig'))
    result = {'profile': metadata.get('profile'),
              'visible_window': metadata.get('visible_window'),
              'cpu_affinity_mask': metadata.get('cpu_affinity_mask'),
              'executable_sha256': metadata.get('executable_sha256'),
              'runtime_binaries_sha256': metadata.get('runtime_binaries_sha256'),
              'matched_scene': False, 'window_seconds': [start, end],
              'stopped_at_limit': metadata.get('stopped_at_limit'),
              'exit_code': metadata.get('exit_code')}
    frames = root/'guest-frames.csv'
    result['guest_submissions'] = summarize(frames, start, end) if frames.is_file() else None
    process = [r for r in read_csv(root/'process.csv') if start <= float(r['elapsed_s']) < end]
    masks = sorted({r.get('cpu_affinity_mask', '') for r in process})
    result['observed_cpu_affinity_masks'] = masks
    requested = metadata.get('cpu_affinity_mask')
    result['cpu_affinity_verified'] = (bool(process) and bool(requested) and
        int(requested, 0) != 0 and all(mask and int(mask, 0) == int(requested, 0) for mask in masks))
    if len(process) >= 2:
        elapsed = float(process[-1]['elapsed_s'])-float(process[0]['elapsed_s'])
        result['mean_process_cpu_cores'] = ((float(process[-1]['cpu_time_s'])-float(process[0]['cpu_time_s']))/elapsed) if elapsed > 0 else None
        result['peak_sampled_working_set_bytes'] = max(int(r['working_set_bytes']) for r in process)
    sensors = [r for r in read_csv(root/'amd.csv') if start <= float(r['second']) < end]
    result['amd_raw_sensor_medians'] = {}
    for key in ('gfx_clock_raw', 'mem_clock_raw', 'gfx_activity_raw', 'edge_temp_raw',
                'hotspot_temp_raw', 'asic_power_raw', 'throttler_raw'):
        values = [float(r[key]) for r in sensors if r.get(key) not in (None, '', 'NA')]
        result['amd_raw_sensor_medians'][key] = statistics.median(values) if values else None
    log_path = root/'runtime.log'
    log = log_path.read_text(encoding='utf-8-sig', errors='replace') if log_path.is_file() else ''
    result['pipeline_creation_log_entries'] = log.count('Creating graphics pipeline state')
    result['placeholder_presentation_skip_entries'] = log.count('Skipping Vulkan frame presentation')
    constant_totals = {}
    stamp = metadata.get('started')
    if stamp:
        begun = datetime.fromisoformat(stamp)
        for line in log.splitlines():
            if 'CH2K8_GPU_CONSTANTS ' not in line:
                continue
            timestamp = re.match(r'\[([^]]+)\]', line)
            if not timestamp:
                continue
            elapsed = (datetime.fromisoformat(timestamp[1]).replace(tzinfo=begun.tzinfo)-begun).total_seconds()
            if not start <= elapsed < end:
                continue
            fields = dict(re.findall(r'(\w+)=(\S+)', line.split('CH2K8_GPU_CONSTANTS ', 1)[1]))
            mode = fields['native']
            totals = constant_totals.setdefault(mode, {'bins': 0})
            totals['bins'] += 1
            for key in ('single', 'ranges', 'words', 'skipped', 'skipped_words',
                        'float_uploads', 'system_uploads', 'bool_uploads', 'bulk_packets', 'packet_words',
                        'fast_packets', 'slow_packets', 'fast_words', 'slow_words', 'fast_ns', 'slow_ns'):
                totals[key] = totals.get(key, 0) + int(fields.get(key, 0))
        for totals in constant_totals.values():
            requests = totals['single'] + totals['ranges']
            totals['skipped_request_fraction'] = totals['skipped']/requests if requests else None
            for variant in ('fast', 'slow'):
                words = totals[variant+'_words']
                totals[variant+'_ns_per_word'] = totals[variant+'_ns']/words if words else None
    result['shader_constant_bins'] = constant_totals
    result['native_readbacks'] = sorted(p.name for p in root.glob('output-*.bmp'))
    result['native_readback_checks'] = [inspect_native_readback(p) for p in sorted(root.glob('output-*.bmp'))]
    result['limits'] = ('Autonomous demo scenes are not locked; guest submission rate is not unique displayed FPS. '
                        'Pipeline log counts are not creation durations. Sensor values retain tool raw units; '
                        'unsupported sensors are null. Native readbacks require visual inspection.')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--start', type=float, default=120)
    parser.add_argument('--end', type=float, default=180)
    args = parser.parse_args()
    if args.start < 0 or args.end <= args.start:
        parser.error('Require 0 <= start < end')
    print(json.dumps(summarize_run(args.run, args.start, args.end), indent=2))
