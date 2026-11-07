"""Resolve bounded IP samples with a matching executable/PDB and source lines."""
import argparse
import csv
import hashlib
import json
import re
import subprocess
from collections import Counter
from pathlib import Path


def pdb_checksums(text):
    result = {}
    for line in text.splitlines():
        match = re.match(r'- \(MD5: ([0-9A-Fa-f]{32})\) (.+)', line.strip())
        if match:
            result.setdefault(match[2].casefold(), set()).add(match[1].lower())
    return result


def summarize(rows, symbols, checksums, source_root=None):
    functions, operations = Counter(), Counter()
    sources = {}
    for row, result in zip(rows, symbols, strict=True):
        frames = result.get('Symbol', [])
        guest = next((f for f in frames if re.match(r'sub_[0-9A-F]{8}', f.get('FunctionName', ''))), None)
        if guest:
            functions[guest['FunctionName']] += 1
        frame = next((f for f in frames if '_recomp.' in f.get('FileName', '') and f.get('Line', 0)), None)
        operation = 'unattributed'
        if frame:
            path = frame['FileName']
            if path not in sources:
                source = source_root / Path(path).name if source_root else Path(path)
                data = source.read_bytes()
                allowed = checksums.get(path.casefold(), set())
                if hashlib.md5(data).hexdigest() not in allowed:
                    raise ValueError(f'Source does not match PDB checksum: {path}; use matching archived sources')
                sources[path] = (data.decode('utf-8').splitlines(), hashlib.sha256(data).hexdigest())
            for line in reversed(sources[path][0][:frame['Line']]):
                if line.startswith('\t// '):
                    operation = line[4:].split()[0]
                    break
        operations[operation] += 1
    return {'guest_function_samples': dict(functions.most_common()),
            'guest_source_operation_samples': dict(operations.most_common()),
            'source_sha256': {path: info[1] for path, info in sources.items()}}


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        while block := stream.read(1024*1024):
            result.update(block)
    return result.hexdigest()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('samples', type=Path)
    parser.add_argument('executable', type=Path)
    parser.add_argument('--symbolizer', default='llvm-symbolizer')
    parser.add_argument('--pdbutil', default='llvm-pdbutil')
    parser.add_argument('--source-root', type=Path, help='Matching archived generated source directory')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    with args.samples.open(encoding='utf-8-sig') as stream:
        rows = list(csv.DictReader(stream))
    selected = [r for r in rows if r['module'].lower() == args.executable.name.lower()]
    process = subprocess.run([args.symbolizer, '--relative-address', '--output-style=JSON',
        '--obj='+str(args.executable.resolve())], input='\n'.join(r['rva'] for r in selected)+'\n',
        capture_output=True, text=True, check=True)
    symbols = [json.loads(line) for line in process.stdout.splitlines() if line.strip()]
    pdb = subprocess.run([args.pdbutil, 'dump', '-files', str(args.executable.with_suffix('.pdb'))],
                         capture_output=True, text=True, check=True)
    result = {'executable_sha256': digest(args.executable), 'samples': len(rows),
              'module_samples': dict(Counter(r['module'] for r in rows).most_common()),
              **summarize(selected, symbols, pdb_checksums(pdb.stdout), args.source_root)}
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps(result, indent=2))
