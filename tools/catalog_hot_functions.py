"""Catalog observed guest functions without copying generated game code."""
import argparse
import csv
import re
from collections import Counter
from pathlib import Path

FUNCTION = re.compile(r'^DEFINE_REX_FUNC\((sub_([0-9A-F]{8}))\) \{', re.M)


def extract(generated):
    functions = {}
    for path in sorted(generated.glob('*_recomp.*.cpp')):
        text = path.read_text(encoding='utf-8')
        for match in FUNCTION.finditer(text):
            # Generated instruction blocks close with indented braces. Stop at
            # the function's own closing brace, excluding adjacent fast copies.
            end = text.index('\n}\n', match.start()) + 3
            functions[match[2]] = text[match.start():end]
    return functions


def catalog(generated, addresses):
    functions = extract(generated)
    for address in addresses:
        address = address.upper().removeprefix('0X')
        text = functions[address]
        operations = Counter(re.findall(r'^\t// (\S+)', text, re.M))
        callers = [caller for caller, body in functions.items()
                   if f'\tsub_{address}(ctx, base);' in body]
        yield {
            'address': f'0x{address}', 'name': f'FUN_{address}',
            'instruction_comments': sum(operations.values()),
            'vector_instruction_comments': sum(n for op, n in operations.items() if op.startswith('v')),
            'stvlx_sites': operations['stvlx'],
            'backward_branches': sum(int(target, 16) <= int(label, 16)
                for label, block in re.findall(r'loc_([0-9A-F]{8}):(.*?)(?=\nloc_|\Z)', text, re.S)
                for target in re.findall(r'goto loc_([0-9A-F]{8});', block)),
            'callers': ';'.join(f'0x{caller}' for caller in callers),
            'common_operations': ';'.join(f'{op}:{n}' for op, n in operations.most_common(10)),
        }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('generated', type=Path)
    parser.add_argument('addresses', nargs='+')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    rows = list(catalog(args.generated, args.addresses))
    with args.output.open('x', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)
