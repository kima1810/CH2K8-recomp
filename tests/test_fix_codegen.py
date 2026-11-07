"""Numeric regression for the SDK's invalid 32-bit/44-bit sign extension."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from fix_codegen import correct_sign_extension


def test_correction_is_narrow_and_idempotent():
    source = "temp.s32 = (int32_t(vTemp.u64[0] << 44) >> 44);\r\n"
    corrected, count = correct_sign_extension(source)
    assert count == 1
    assert "int64_t" in corrected
    assert corrected.endswith("\r\n")
    assert correct_sign_extension(corrected) == (corrected, 0)
    unrelated = "temp.s32 = (int32_t(vTemp.u64[0] << 4) >> 4);"
    assert correct_sign_extension(unrelated) == (unrelated, 0)


def test_noop_correction_keeps_source_and_dependency_stamp_unchanged(tmp_path):
    generated = tmp_path / "generated"
    generated.mkdir()
    source = generated / "test_recomp.0.cpp"
    source.write_bytes(b"temp.s32 = (int32_t(vTemp.u64[0] << 44) >> 44);\r\n")
    stamp = tmp_path / "correction.stamp"
    tool = Path(__file__).resolve().parents[1] / "tools/fix_codegen.py"
    command = [sys.executable, str(tool), str(generated), "--stamp", str(stamp)]
    subprocess.run(command, check=True, capture_output=True, text=True)
    assert b"int64_t" in source.read_bytes()
    before = 1_700_000_000_000_000_000
    for path in (source, stamp):
        os.utime(path, ns=(before, before))
    subprocess.run(command, check=True, capture_output=True, text=True)
    assert source.stat().st_mtime_ns == before
    assert stamp.stat().st_mtime_ns == before


def test_signed_20bit_lanes_compile_and_match_reference(tmp_path):
    compiler = shutil.which("clang++")
    if not compiler:
        pytest.skip("clang++ is needed for the generated-expression numeric test")
    statements = "\n".join(
        f"temp.s32 = (int32_t(vTemp.u64[0] << {shift}) >> 44); "
        f"result[{lane}] = temp.s32;"
        for lane, shift in enumerate((44, 24, 4))
    )
    corrected, count = correct_sign_extension(statements)
    assert count == 3
    cases = [
        (0, 0, 0),
        (1, -1, 7),
        (-524288, 524287, -524288),
        (524287, -524288, 524287),
        (-1, -1, -1),
    ]
    checks = []
    for lanes in cases:
        packed = sum((lane & 0xFFFFF) << (20 * i) for i, lane in enumerate(lanes))
        # Set the fourth packed component too, ensuring it cannot contaminate XYZ.
        packed |= 0xA << 60
        checks.append(f"unpack(0x{packed:016x}ULL, result);")
        checks.extend(f"assert(result[{i}] == {lane});" for i, lane in enumerate(lanes))
    source = tmp_path / "sign_extension.cpp"
    executable = tmp_path / ("sign_extension.exe" if sys.platform == "win32" else "sign_extension")
    source.write_text(
        "#include <cstdint>\n#include <cassert>\n"
        "void unpack(uint64_t packed, int32_t* result) {\n"
        "struct { uint64_t u64[1]; } vTemp = {{packed}};\n"
        "struct { int32_t s32; } temp{};\n" + corrected + "\n}\n"
        "int main() { int32_t result[3];\n" + "\n".join(checks) + "\n}\n",
        encoding="utf-8",
    )
    subprocess.run(
        [compiler, "-std=c++23", "-O2", "-Werror=shift-count-overflow", str(source), "-o", str(executable)],
        check=True, capture_output=True, text=True,
    )
    subprocess.run([str(executable)], check=True, capture_output=True, text=True)
