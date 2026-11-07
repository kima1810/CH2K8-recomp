"""Correct the pinned ReXGlue SDK's vupkd3d128 packed-64 translation.

The SDK emits a 32-bit cast followed by a 44-bit right shift. Widening that
cast preserves the shifted 64-bit value until after arithmetic sign extension.
The complete type-6 block also needs its source half, output lanes, biased
float bits, and negative-overflow NaNs corrected. Only exact pinned emission
shapes are eligible. No game bytes are read.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path


BROKEN_SIGN_EXTENSION = re.compile(
    r"(\b\w+\.s32 = \()int32_t(\(\w+\.u64\[0\] << (?:44|24|4)\) >> 44\);)"
)

# Exact pinned-SDK type-6 block; accept both raw and earlier shift-corrected text.
PACKED64_UNPACK = re.compile(
    r"(?P<indent>\t)// vupkd3d128 (?P<dst>v\d+),(?P<src>v\d+),24\n"
    r"\tvTemp\.u64\[0\] = ctx\.(?P=src)\.u64\[1\];\n"
    r"\ttemp\.s32 = \(int(?:32|64)_t\(vTemp\.u64\[0\] << 44\) >> 44\);\n"
    r"\tctx\.(?P=dst)\.f32\[0\] = float\(temp\.s32\);\n"
    r"\ttemp\.s32 = \(int(?:32|64)_t\(vTemp\.u64\[0\] << 24\) >> 44\);\n"
    r"\tctx\.(?P=dst)\.f32\[1\] = float\(temp\.s32\);\n"
    r"\ttemp\.s32 = \(int(?:32|64)_t\(vTemp\.u64\[0\] << 4\) >> 44\);\n"
    r"\tctx\.(?P=dst)\.f32\[2\] = float\(temp\.s32\);\n"
    r"\tctx\.(?P=dst)\.f32\[3\] = float\(vTemp\.u64\[0\] >> 60\);"
)


def correct_packed64_unpack(source: str) -> tuple[str, int]:
    def replacement(match: re.Match) -> str:
        dst, src = match['dst'], match['src']
        lines = [f'\t// vupkd3d128 {dst},{src},24',
                 f'\tvTemp.u64[0] = ctx.{src}.u64[0];']
        for lane, shift in zip((3, 2, 1), (44, 24, 4)):
            lines.extend([
                f'\ttemp.s32 = (int64_t(vTemp.u64[0] << {shift}) >> 44);',
                f'\tctx.{dst}.u32[{lane}] = temp.s32 == -524288 ? 0x7FC00000u : uint32_t(temp.s32 + 0x40400000);',
            ])
        lines.append(f'\tctx.{dst}.u32[0] = uint32_t(vTemp.u64[0] >> 60) + 0x3F800000u;')
        return '\n'.join(lines)
    return PACKED64_UNPACK.subn(replacement, source)


PACKED64_PACK = re.compile(
    r"\t// vpkd3d128 (?P<dst>v\d+),(?P<src>v\d+),6,2,(?P<shift>[02])\n"
    r"\tvTemp\.u64\[0\] = 0;\n"
    r"\ttemp\.s32 = int32_t\(ctx\.(?P=src)\.f32\[0\]\);\n"
    r"\tvTemp\.u64\[0\] = uint64_t\(temp\.s32 & 0xFFFFF\);\n"
    r"\ttemp\.s32 = int32_t\(ctx\.(?P=src)\.f32\[1\]\);\n"
    r"\tvTemp\.u64\[0\] \|= uint64_t\(temp\.s32 & 0xFFFFF\) << 20;\n"
    r"\ttemp\.s32 = int32_t\(ctx\.(?P=src)\.f32\[2\]\);\n"
    r"\tvTemp\.u64\[0\] \|= uint64_t\(temp\.s32 & 0xFFFFF\) << 40;\n"
    r"\ttemp\.s32 = int32_t\(ctx\.(?P=src)\.f32\[3\]\);\n"
    r"\tvTemp\.u64\[0\] \|= uint64_t\(temp\.s32 & 0xF\) << 60;\n"
    r"\tctx\.(?P=dst)\.u64\[(?P<half>[01])\] = vTemp\.u64\[0\];"
)


def correct_packed64_pack(source: str) -> tuple[str, int]:
    def replacement(match: re.Match) -> str:
        dst, src, shift = match['dst'], match['src'], int(match['shift'])
        if int(match['half']) != shift // 2:
            return match[0]
        lines = [f'\t// vpkd3d128 {dst},{src},6,2,{shift}', '\tvTemp.u64[0] = 0;']
        for component, lane in enumerate((3, 2, 1, 0)):
            minimum = '0x40380001u' if component < 3 else '0x40400000u'
            maximum = '0x4047FFFFu' if component < 3 else '0x4040000Fu'
            mask = '0xFFFFFu' if component < 3 else '0xFu'
            lines.extend([
                f'\ttemp.u32 = ctx.{src}.u32[{lane}];',
                f'\tvTemp.u32[2] = {minimum};',
                '\tif (!(temp.f32 >= vTemp.f32[2])) temp.u32 = vTemp.u32[2];',
                f'\tvTemp.u32[2] = {maximum};',
                '\tif (temp.f32 > vTemp.f32[2]) temp.u32 = vTemp.u32[2];',
                f'\tvTemp.u64[0] |= uint64_t(temp.u32 & {mask}) << {component * 20};',
            ])
        lines.append(f'\tctx.{dst}.u64[{shift // 2}] = vTemp.u64[0];')
        return '\n'.join(lines)
    return PACKED64_PACK.subn(replacement, source)


def correct_sign_extension(source: str) -> tuple[str, int]:
    return BROKEN_SIGN_EXTENSION.subn(r"\1int64_t\2", source)


def correct_directory(generated: Path) -> tuple[int, int]:
    sources = sorted(generated.glob("*_recomp.*.cpp"))
    if not sources:
        raise ValueError(f"No recompiled sources found in {generated}")
    total = 0
    changed = 0
    for path in sources:
        original = path.read_bytes()
        corrected, count = correct_packed64_unpack(original.decode("utf-8"))
        corrected, packs = correct_packed64_pack(corrected)
        count += packs
        corrected, shifts = correct_sign_extension(corrected)
        count += shifts
        if count:
            path.write_bytes(corrected.encode("utf-8"))
            total += count
            changed += 1
    return total, changed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("generated", type=Path, help="Generated default/ directory")
    parser.add_argument("--stamp", type=Path, help="Touch when corrected output changes")
    args = parser.parse_args()
    total, changed = correct_directory(args.generated)
    print(f"vupkd3d128: corrected {total} expressions in {changed} files")
    if args.stamp and (total or not args.stamp.exists()):
        args.stamp.parent.mkdir(parents=True, exist_ok=True)
        args.stamp.touch()


if __name__ == "__main__":
    main()
