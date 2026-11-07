"""Summarize same-capture shader counters; action sums are not displayed FPS."""
import argparse
import csv
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path


def summarize(path, target):
    grouped = defaultdict(dict)
    for row in csv.DictReader(Path(path).open(), delimiter='\t'):
        key = (int(row['trial']), row['variant'])
        event, value = int(row['event']), float(row['ms'])
        if key[1] not in ('original', 'specialized') or not math.isfinite(value) or value < 0:
            raise ValueError('Invalid shader counter row')
        if event in grouped[key]:
            raise ValueError('Duplicate event in trial')
        grouped[key][event] = value
    trials = sorted({key[0] for key in grouped})
    if len(trials) < 3:
        raise ValueError('Require three warmed paired trials')
    result = []
    for trial in trials:
        old, new = grouped[(trial, 'original')], grouped[(trial, 'specialized')]
        if set(old) != set(new) or target not in old:
            raise ValueError('Mismatched action sets or missing target')
        a, b = sum(old.values()), sum(new.values())
        if a <= 0 or old[target] <= 0:
            raise ValueError('Nonpositive baseline')
        result.append({'trial': trial, 'actions': len(old), 'original_sum_ms': a,
                       'specialized_sum_ms': b, 'sum_reduction': 1-b/a,
                       'original_target_ms': old[target], 'specialized_target_ms': new[target],
                       'target_reduction': 1-new[target]/old[target]})
    return {'trials': result,
            'median_sum_reduction': statistics.median(r['sum_reduction'] for r in result),
            'median_target_reduction': statistics.median(r['target_reduction'] for r in result),
            'limits': 'Same recorded workload, one shader replacement. GPU action sums exclude gaps and are not displayed FPS. EDRAM equality must be established separately before timing.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path', type=Path)
    parser.add_argument('--target', type=int, required=True)
    args = parser.parse_args()
    print(json.dumps(summarize(args.path, args.target), indent=2))
