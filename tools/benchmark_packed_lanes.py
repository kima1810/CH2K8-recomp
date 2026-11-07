"""Compare current packed-vector helpers with the shipped SIMD lane layout.

Reuses the scalar differential checks and alternating timing trials in the
existing C++ benchmarks. Generated sources, executables and results stay in out/.
"""
import argparse
import csv
import io
import json
import shutil
import statistics
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = '7d6ea05'


def benchmark(compiler, output):
    output.mkdir(parents=True, exist_ok=False)
    previous = subprocess.run(
        ['git', 'show', REFERENCE + ':port/src/packed_vector_optimized.h'],
        cwd=ROOT, capture_output=True, text=True, check=True).stdout
    previous = previous.split('// Selected once per guest function call', 1)[0]
    previous = previous.replace('Ch2k8PackBiased64', 'PreviousPack')
    previous = previous.replace('Ch2k8UnpackBiased64', 'PreviousUnpack')
    (output / 'packed_vector_previous.h').write_text(previous)
    flags = ['-std=c++23', '-O2', '-DNDEBUG', '-fwrapv',
             '-fno-strict-aliasing', '-ffp-model=strict', '-msse4.1',
             '-DNOMINMAX', '-DSPDLOG_FMT_EXTERNAL', '-DSPDLOG_COMPILED_LIB',
             '-I', str(ROOT / 'port/src'), '-I', str(ROOT / 'port/sdk-vulkan/include')]
    result = {'reference': REFERENCE, 'compiler': compiler, 'flags': flags,
              'limits': 'Local helper timings, not gameplay FPS or matched-scene measurements.'}
    for operation, name in [('pack', 'PreviousPack'), ('unpack', 'PreviousUnpack')]:
        source = (ROOT / f'tools/benchmark_vector_{operation}.cpp').read_text()
        source = source.replace('#include "packed_vector_optimized.h"',
                                '#include "packed_vector_optimized.h"\n'
                                '#include "packed_vector_previous.h"')
        # check() retains the scalar oracle. Only the timed control changes.
        source = source.replace('scalar(result, value, temporary, scratch',
                                name + '(result, value, temporary, scratch')
        cpp = output / f'{operation}.cpp'
        executable = output / f'{operation}.exe'
        cpp.write_text(source)
        subprocess.run([compiler, *flags, str(cpp), '-o', str(executable)], check=True)
        measured = subprocess.run([str(executable)], capture_output=True, text=True, check=True)
        (output / f'{operation}.csv').write_text(measured.stdout)
        lines = measured.stdout.splitlines()
        if not lines[0].startswith('validated_vectors,'):
            raise ValueError('Missing differential validation result')
        rows = list(csv.DictReader(io.StringIO('\n'.join(lines[1:]))))
        baseline = statistics.median(float(row['baseline_ns']) for row in rows)
        optimized = statistics.median(float(row['optimized_ns']) for row in rows)
        result[operation] = {'validated_vectors': int(lines[0].split(',')[1]),
                             'previous_ns': baseline, 'current_ns': optimized,
                             'median_paired_reduction_percent': statistics.median(
                                 100 * (1 - float(row['optimized_ns']) / float(row['baseline_ns']))
                                 for row in rows)}
    (output / 'summary.json').write_text(json.dumps(result, indent=2))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', default=shutil.which('clang++'))
    parser.add_argument('--output', type=Path, default=ROOT / 'out' /
                        ('packed-lanes-' + datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')))
    args = parser.parse_args()
    if not args.compiler:
        parser.error('clang++ is required')
    print(json.dumps(benchmark(args.compiler, args.output.resolve()), indent=2))
