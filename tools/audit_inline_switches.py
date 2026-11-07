"""Compare Ghidra's validated inline tables with generated switch prefixes.

Only emit a hint when every existing case agrees and the generator omitted a
suffix. Register disagreements or changed targets are reported, not repaired.
"""
from __future__ import annotations

import argparse
import re
import tomllib
from pathlib import Path


DISPATCH = re.compile(
    r"// lis r12,(-?\d+)\n[^\n]*\n\s*// addi r12,r12,(-?\d+)\n[^\n]*\n"
    r"\s*// rlwinm r0,r(\d+),2,0,29\n(?:[^\n]*\n){6}"
    r"\s*switch \(ctx\.r(\d+)\.u32\) \{(.*?)\n\t\}", re.S
)


def read_emitted(source: str) -> dict:
    emitted = {}
    for match in DISPATCH.finditer(source):
        table = ((int(match[1]) << 16) + int(match[2])) & 0xFFFFFFFF
        entries = re.findall(r"case (\d+):\s*goto loc_([0-9A-F]+);", match[5])
        if len(entries) != len(re.findall(r"case \d+:", match[5])):
            continue
        entries = sorted((int(index), int(address, 16)) for index, address in entries)
        if [index for index, _ in entries] != list(range(len(entries))):
            continue
        start = source.rfind("DEFINE_REX_FUNC(", 0, match.start())
        if start < 0:
            continue
        start += len("DEFINE_REX_FUNC(")
        emitted[table] = {"register": int(match[4]), "labels": [a for _, a in entries],
                          "function": source[start:source.index(")", start)]}
    return emitted


def classify(tables: list, emitted: dict) -> tuple[list, list]:
    truncated, disagreements = [], []
    for table in tables:
        current = emitted.get(table["address"] + 4)
        if current is None:
            continue
        labels = current["labels"]
        if current["register"] != table["register"]:
            disagreements.append(table)
        elif labels == table["labels"]:
            continue
        elif labels and len(labels) < len(table["labels"]) and labels == table["labels"][:len(labels)]:
            truncated.append(dict(table, previous_count=len(labels), function=current["function"]))
        else:
            disagreements.append(table)
    return truncated, disagreements


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tables", type=Path, help="TOML from ExportInlineSwitches.java")
    parser.add_argument("generated", type=Path)
    parser.add_argument("--output", type=Path, help="New TOML hints file; never overwrites")
    args = parser.parse_args()
    tables = tomllib.loads(args.tables.read_text(encoding="utf-8"))["switch_tables"]
    emitted = {}
    for source in args.generated.glob("*_recomp.*.cpp"):
        emitted.update(read_emitted(source.read_text(encoding="utf-8")))
    truncated, disagreements = classify(tables, emitted)
    compared = sum(table["address"] + 4 in emitted for table in tables)
    print(f"Validated tables: {len(tables)}; compared: {compared}; truncated prefixes: {len(truncated)}; disagreements: {len(disagreements)}")
    if args.output:
        with args.output.open("x", encoding="utf-8", newline="\n") as out:
            out.write("# [CONFIRMED] Raw inline pointers from Ghidra; existing generated cases match each prefix.\n")
            out.write("# ExportInlineSwitches.java + tools/audit_inline_switches.py; retail USA XEX.\n")
            out.write("# Evidence: docs/findings/2026-10-30-native-build-and-control-flow.md.\n")
            for table in truncated:
                out.write(f"\n# {table['function']}: {table['previous_count']} -> {len(table['labels'])} cases.\n")
                out.write(f"[[switch_tables]]\naddress = 0x{table['address']:08X}\nregister = {table['register']}\nlabels = [")
                for i, address in enumerate(table["labels"]):
                    if i:
                        out.write(",\n          " if i % 8 == 0 else ", ")
                    out.write(f"0x{address:08X}")
                out.write("]\n")


if __name__ == "__main__":
    main()
