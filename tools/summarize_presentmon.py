"""Summarize PresentMon CPU/GPU timings without treating host presents as game FPS."""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path


def summarize(path: Path, start: float = 0, end: float = math.inf) -> list[dict]:
    chains = defaultdict(list)
    with path.open(encoding='utf-8-sig', newline='') as stream:
        for row in csv.DictReader(stream):
            time = row.get('TimeInMs', row.get('CPUStartTimeInMs', row.get('CPUStartTime', '')))
            try:
                seconds = float(time) / 1000
            except (ValueError, TypeError):
                continue
            if start <= seconds < end:
                chains[(row.get('ProcessID'), row.get('SwapChainAddress'))].append((seconds, row))
    output = []
    for (process, chain), rows in chains.items():
        span = max(x[0] for x in rows) - min(x[0] for x in rows)
        result = {'process': process, 'swap_chain': chain, 'rows': len(rows),
                  'span_seconds': span, 'host_presents_per_second': (len(rows)-1)/span if span else None,
                  'metrics_ms': {}}
        for metric in ('MsBetweenPresents', 'MsCPUBusy', 'MsCPUWait', 'MsGPUTime', 'MsGPUBusy', 'MsGPUWait', 'MsInPresentAPI'):
            values = []
            for _, row in rows:
                try:
                    value = float(row.get(metric, ''))
                    if math.isfinite(value) and value >= 0:
                        values.append(value)
                except (ValueError, TypeError):
                    pass
            if values:
                values.sort()
                result['metrics_ms'][metric] = {'count': len(values), 'mean': sum(values)/len(values),
                    'p50': values[(len(values)-1)//2], 'p95': values[math.ceil(.95*len(values))-1],
                    'p99': values[math.ceil(.99*len(values))-1], 'max': values[-1],
                    'at_least_16_7_ms': sum(value >= 16.7 for value in values),
                    'at_least_100_ms': sum(value >= 100 for value in values)}
        output.append(result)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv', type=Path)
    parser.add_argument('--start', type=float, default=0, help='Seconds on the PresentMon capture timeline')
    parser.add_argument('--end', type=float, default=math.inf)
    args = parser.parse_args()
    print(json.dumps(summarize(args.csv, args.start, args.end), indent=2))


if __name__ == '__main__':
    main()
