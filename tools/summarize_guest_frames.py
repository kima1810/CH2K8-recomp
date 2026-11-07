"""Summarize opt-in guest VdSwap cadence; these are submissions, not display FPS."""
import argparse
import csv
import json
import math
from pathlib import Path


def summarize(path, start=0.0, end=math.inf):
    with Path(path).open(encoding='utf-8-sig') as stream:
        rows = [row for row in csv.DictReader(stream)
                if start <= float(row['elapsed_ms'])/1000 < end]
    result = {'submissions': len(rows), 'metrics_ms': {}}
    for key in ('submit_interval_ms', 'swap_wall_ms', 'swap_thread_cpu_ms'):
        values = sorted(float(row[key]) for row in rows
                        if math.isfinite(float(row[key])) and float(row[key]) >= 0
                        and (key != 'submit_interval_ms' or float(row[key]) > 0))
        if values:
            result['metrics_ms'][key] = {'p50': values[(len(values)-1)//2],
                'p95': values[math.ceil(len(values)*.95)-1], 'mean': sum(values)/len(values)}
    interval = result['metrics_ms'].get('submit_interval_ms', {}).get('p50')
    result['median_submission_hz'] = 1000/interval if interval else None
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv', type=Path)
    parser.add_argument('--start', type=float, default=0)
    parser.add_argument('--end', type=float, default=math.inf)
    args = parser.parse_args()
    print(json.dumps(summarize(args.csv, args.start, args.end), indent=2))
