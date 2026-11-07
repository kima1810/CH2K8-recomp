"""Summarize interleaved hot-function timings; no gameplay FPS claim implied."""
import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path


def summarize(path, start=0, end=float('inf')):
    totals = defaultdict(lambda: {'calls': 0, 'work_units': 0, 'wall_ns': 0,
                                 'wide_stores': 0, 'byte_stores': 0})
    with Path(path).open(encoding='utf-8-sig') as stream:
        for row in csv.DictReader(stream):
            if not start <= float(row['elapsed_ms'])/1000 < end:
                continue
            variant = 'normalization_batch' if row.get('normalization_batch') == '1' else 'native_ram' if row.get('ram_optimized') == '1' else 'pack_unpack_store' if row.get('store_optimized') == '1' else 'pack_unpack' if row.get('unpack_optimized') == '1' else 'optimized' if row['optimized'] == '1' else 'baseline'
            total = totals[(row['function'], variant)]
            for key in total:
                total[key] += int(row.get(key, 0))
    result = {}
    for (address, variant), total in sorted(totals.items()):
        total['ns_per_call'] = total['wall_ns']/total['calls'] if total['calls'] else None
        total['ns_per_work_unit'] = total['wall_ns']/total['work_units'] if total['work_units'] else None
        result.setdefault(address, {})[variant] = total
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv', type=Path)
    parser.add_argument('--start', type=float, default=0)
    parser.add_argument('--end', type=float, default=float('inf'))
    args = parser.parse_args()
    print(json.dumps(summarize(args.csv, args.start, args.end), indent=2))
