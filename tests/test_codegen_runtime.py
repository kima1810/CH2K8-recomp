"""Optional execution checks against locally generated code; no game data committed."""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


def test_generated_startup_loop_reaches_cases_eight_and_nine(tmp_path):
    root = Path(__file__).resolve().parents[1]
    generated = root / "port/generated/default"
    sdk = root / "port/sdk/include"
    compiler = shutil.which("clang++")
    if sys.platform != "win32" or not compiler or not sdk.is_dir() or not generated.is_dir():
        pytest.skip("Requires Windows, local ReXGlue SDK, generated game code, and clang++")
    signature = "DEFINE_REX_FUNC(sub_84D36860) {"
    body = None
    for path in generated.glob("*_recomp.*.cpp"):
        source = path.read_text(encoding="utf-8")
        if signature in source:
            start = source.index(signature)
            body = source[start:source.index("\n}\n", start) + 3]
            break
    assert body is not None, "Startup loop missing from generated code"

    # Independent layout calculation from the original ten-entry tables.
    alignment = [16, 16, 1, 52, 16, 16, 1, 52, 4, 4]
    count = [256, 32, 128, 26, 256, 32, 128, 10, 96, 4]
    size = 200
    for index in range(10):
        if index in (3, 7):
            continue
        unit = alignment[index]
        size = ((size + unit - 1) // unit) * unit + unit * count[index]
        size = ((size + 7) // 8) * 8 + ((count[index] + 63) // 64) * 16
    expected = ((size + 3) // 4) * 4 + 512
    assert expected == 10864

    source = tmp_path / "startup_loop.cpp"
    executable = tmp_path / ("startup_loop.exe" if sys.platform == "win32" else "startup_loop")
    source.write_text(
        '#include "ch2k8_pch.h"\n#include <windows.h>\n' + body + "\n"
        "int main() { PPCContext ctx{};\n"
        "auto memory = static_cast<uint8_t*>(VirtualAlloc(nullptr, 1ull << 32, MEM_RESERVE, PAGE_NOACCESS));\n"
        "if (!memory) return 2;\n"
        "if (!VirtualAlloc(memory + 0x84D36000u, 4096, MEM_COMMIT, PAGE_READWRITE)) return 3;\n"
        "sub_84D36860(ctx, memory);\n"
        "VirtualFree(memory, 0, MEM_RELEASE);\n"
        f"return ctx.r3.u32 == {expected} ? 0 : 1; }}\n",
        encoding="utf-8",
    )
    compilation = subprocess.run(
        [compiler, "-std=c++23", "-O2", "-msse4.1", "-DNOMINMAX", "-DWIN32_LEAN_AND_MEAN",
         "-DSPDLOG_FMT_EXTERNAL", "-DSPDLOG_COMPILED_LIB",
         "-I", str(sdk), "-I", str(generated), str(source), "-o", str(executable)],
        capture_output=True, text=True,
    )
    assert compilation.returncode == 0, compilation.stderr
    execution = subprocess.run([str(executable)], capture_output=True, text=True)
    assert execution.returncode == 0, f"Generated loop failed: {execution.returncode}, {execution.stderr}"


def test_generated_gameplay_thunks_preserve_arguments_and_return_path(tmp_path):
    root = Path(__file__).resolve().parents[1]
    generated = root / "port/generated/default"
    sdk = root / "port/sdk/include"
    compiler = shutil.which("clang++")
    if sys.platform != "win32" or not compiler or not sdk.is_dir() or not generated.is_dir():
        pytest.skip("Requires Windows, local ReXGlue SDK, generated game code, and clang++")
    thunks = {
        0x8471B0A8: (0x84718B80, 'zero'),
        0x8471B0B0: (0x84718B90, 'zero'),
        0x8471B0B8: (0x84718B60, True),
        0x8471B0C0: (0x84718B70, True),
        0x8471B0C8: (0x84718B80, True),
        0x8471B0D0: (0x84718B90, True),
        0x8471B0D8: (0x84718B10, False),
        0x8471B0F8: (0x847187A8, True),
        0x8471B100: (0x8471A1B0, True),
        0x8471B108: (0x84718AE0, False),
        0x8471B2E8: (0x84718DD0, True),
        0x8471B2F0: (0x84718E20, False),
        0x8471B300: (0x84718EA0, True),
        0x8471B308: (0x84718EC0, False),
    }
    bodies = {}
    for path in generated.glob("*_recomp.*.cpp"):
        text = path.read_text(encoding="utf-8")
        for address in thunks:
            signature = f"DEFINE_REX_FUNC(sub_{address:08X}) {{"
            if signature in text:
                start = text.index(signature)
                bodies[address] = text[start:text.index("\n}\n", start) + 3]
        if len(bodies) == len(thunks):
            break
    assert set(bodies) == set(thunks), "Gameplay thunk absent from generated sources"
    mappings = (generated / "ch2k8_init.cpp").read_text(encoding="utf-8")
    stubs, checks = {}, []
    for address, (target, masks_byte) in thunks.items():
        assert f"{{ 0x{address:08X}, sub_{address:08X} }}" in mappings
        stubs[target] = (
            f'extern "C" void sub_{target:08X}(PPCContext& ctx, uint8_t*) {{ '
            f"observed = ctx.r3.u64; destination = 0x{target:08X}; ctx.r3.u64 = 0xCAFE; }}"
        )
        expected = "0" if masks_byte == 'zero' else "0x88" if masks_byte else "0x1122334455667788ULL"
        checks.append(
            "ctx.r3.u64 = 0x1122334455667788ULL; ctx.r4.u64 = 0xAABB; ctx.lr = 0x12345678;\n"
            f"sub_{address:08X}(ctx, memory);\n"
            f"assert(observed == {expected} && destination == 0x{target:08X});\n"
            "assert(ctx.r3.u64 == 0xCAFE && ctx.r4.u64 == 0xAABB && ctx.lr == 0x12345678);\n"
        )
    source = tmp_path / "gameplay_thunks.cpp"
    executable = tmp_path / "gameplay_thunks.exe"
    source.write_text(
        '#include "ch2k8_pch.h"\nstatic uint64_t observed; static uint32_t destination;\n'
        + "\n".join(stubs.values()) + "\n" + "\n".join(bodies.values())
        + "\nint main() { PPCContext ctx{}; alignas(32) uint8_t memory[32]{};\n"
        + "\n".join(checks) + "\n}\n", encoding="utf-8",
    )
    compilation = subprocess.run(
        [compiler, "-std=c++23", "-O2", "-msse4.1", "-DNOMINMAX", "-DWIN32_LEAN_AND_MEAN",
         "-DSPDLOG_FMT_EXTERNAL", "-DSPDLOG_COMPILED_LIB", "-I", str(sdk), "-I", str(generated),
         str(source), "-o", str(executable)], capture_output=True, text=True,
    )
    assert compilation.returncode == 0, compilation.stderr
    execution = subprocess.run([str(executable)], capture_output=True, text=True)
    assert execution.returncode == 0, f"Generated thunk failed: {execution.returncode}, {execution.stderr}"


def test_generated_arena_callbacks_preserve_both_flag_paths(tmp_path):
    root = Path(__file__).resolve().parents[1]
    generated = root / "port/generated/default"
    sdk = root / "port/sdk/include"
    compiler = shutil.which("clang++")
    if sys.platform != "win32" or not compiler or not sdk.is_dir() or not generated.is_dir():
        pytest.skip("Requires Windows, local ReXGlue SDK, generated game code, and clang++")
    addresses = (0x848B6F98, 0x848B6FA0)
    bodies = {}
    for path in generated.glob("*_recomp.*.cpp"):
        text = path.read_text(encoding="utf-8")
        for address in addresses:
            signature = f"DEFINE_REX_FUNC(sub_{address:08X}) {{"
            if signature in text:
                start = text.index(signature)
                bodies[address] = text[start:text.index("\n}\n", start) + 3]
        if len(bodies) == len(addresses):
            break
    assert set(bodies) == set(addresses)
    mappings = (generated / "ch2k8_init.cpp").read_text(encoding="utf-8")
    for address in addresses:
        assert f"{{ 0x{address:08X}, sub_{address:08X} }}" in mappings
    stubs = []
    for target in (0x84B85818, 0x84B85808, 0x84B85C28):
        stubs.append(
            f'extern "C" void sub_{target:08X}(PPCContext& ctx, uint8_t*) {{ '
            f"observed = ctx.r3.u64; destination = 0x{target:08X}; ctx.r3.u64 = 0xCAFE; }}"
        )
    source = tmp_path / "arena_callbacks.cpp"
    executable = tmp_path / "arena_callbacks.exe"
    source.write_text(
        '#include "ch2k8_pch.h"\nstatic uint64_t observed; static uint32_t destination;\n'
        + "\n".join(stubs) + "\n" + "\n".join(bodies.values()) + "\n"
        "int main() { PPCContext ctx{}; alignas(32) uint8_t memory[128]{};\n"
        "const uint32_t flags[] = {0, 0x4000, 0x2000, 0x6000};\n"
        "for (uint32_t flag : flags) {\n"
        "*reinterpret_cast<uint32_t*>(memory + 0x38) = __builtin_bswap32(flag);\n"
        "ctx.r4.u64 = 0x20; ctx.r6.u64 = 0x1122334455667788ULL; ctx.lr = 0x12345678;\n"
        "sub_848B6FA0(ctx, memory);\n"
        "assert(destination == ((flag & 0x4000) ? 0x84B85808u : 0x84B85C28u));\n"
        "assert(observed == 0x1122334455667788ULL && ctx.r3.u64 == 0xCAFE);\n"
        "assert(ctx.r4.u64 == 0x20 && ctx.r6.u64 == observed && ctx.lr == 0x12345678);\n"
        "}\nsub_848B6F98(ctx, memory);\n"
        "assert(destination == 0x84B85818 && observed == ctx.r6.u64 && ctx.r3.u64 == 0xCAFE);\n"
        "assert(ctx.lr == 0x12345678);\n}\n", encoding="utf-8",
    )
    compilation = subprocess.run(
        [compiler, "-std=c++23", "-O2", "-msse4.1", "-DNOMINMAX", "-DWIN32_LEAN_AND_MEAN",
         "-DSPDLOG_FMT_EXTERNAL", "-DSPDLOG_COMPILED_LIB", "-I", str(sdk), "-I", str(generated),
         str(source), "-o", str(executable)], capture_output=True, text=True,
    )
    assert compilation.returncode == 0, compilation.stderr
    execution = subprocess.run([str(executable)], capture_output=True, text=True)
    assert execution.returncode == 0, f"Arena callback failed: {execution.returncode}, {execution.stderr}"


def test_generated_flag_callback_clears_only_low_bit(tmp_path):
    root = Path(__file__).resolve().parents[1]
    generated = root / "port/generated/default"
    sdk = root / "port/sdk/include"
    compiler = shutil.which("clang++")
    if sys.platform != "win32" or not compiler or not sdk.is_dir() or not generated.is_dir():
        pytest.skip("Requires Windows, local ReXGlue SDK, generated game code, and clang++")
    signature = "DEFINE_REX_FUNC(sub_848E3A00) {"
    body = None
    for path in generated.glob("*_recomp.*.cpp"):
        text = path.read_text(encoding="utf-8")
        if signature in text:
            start = text.index(signature)
            body = text[start:text.index("\n}\n", start) + 3]
            break
    assert body is not None
    assert "{ 0x848E3A00, sub_848E3A00 }" in (generated / "ch2k8_init.cpp").read_text()
    source = tmp_path / "flag_callback.cpp"
    executable = tmp_path / "flag_callback.exe"
    source.write_text(
        '#include "ch2k8_pch.h"\n' + body
        + "\nint main() { PPCContext ctx{}; alignas(32) uint8_t memory[256]{};\n"
        "*reinterpret_cast<uint32_t*>(memory + 0x30) = __builtin_bswap32(0x80u);\n"
        "const uint32_t values[] = {0, 1, 2, 3, 0x80000001, 0xFFFFFFFF};\n"
        "for (uint32_t value : values) {\n"
        "*reinterpret_cast<uint32_t*>(memory + 0x9C) = __builtin_bswap32(value);\n"
        "memory[0x9B] = 0xAB; memory[0xA0] = 0xCD;\n"
        "ctx.r3.u64 = 0x20; ctx.r4.u64 = 0xAABB; ctx.lr = 0x12345678;\n"
        "sub_848E3A00(ctx, memory);\n"
        "assert(__builtin_bswap32(*reinterpret_cast<uint32_t*>(memory + 0x9C)) == (value & ~1u));\n"
        "assert(memory[0x9B] == 0xAB && memory[0xA0] == 0xCD);\n"
        "assert(ctx.r3.u64 == 0x20 && ctx.r4.u64 == 0xAABB && ctx.lr == 0x12345678);\n"
        "}\n}\n", encoding="utf-8",
    )
    compilation = subprocess.run(
        [compiler, "-std=c++23", "-O2", "-msse4.1", "-DNOMINMAX", "-DWIN32_LEAN_AND_MEAN",
         "-DSPDLOG_FMT_EXTERNAL", "-DSPDLOG_COMPILED_LIB", "-I", str(sdk), "-I", str(generated),
         str(source), "-o", str(executable)], capture_output=True, text=True,
    )
    assert compilation.returncode == 0, compilation.stderr
    execution = subprocess.run([str(executable)], capture_output=True, text=True)
    assert execution.returncode == 0, f"Flag callback failed: {execution.returncode}, {execution.stderr}"


def test_generated_script_callback_loads_global_and_tail_calls(tmp_path):
    root = Path(__file__).resolve().parents[1]
    generated = root / "port/generated/default"
    sdk = root / "port/sdk/include"
    compiler = shutil.which("clang++")
    if sys.platform != "win32" or not compiler or not sdk.is_dir() or not generated.is_dir():
        pytest.skip("Requires Windows, local ReXGlue SDK, generated game code, and clang++")
    signature = "DEFINE_REX_FUNC(sub_84AB8CA8) {"
    body = None
    for path in generated.glob("*_recomp.*.cpp"):
        text = path.read_text(encoding="utf-8")
        if signature in text:
            start = text.index(signature)
            body = text[start:text.index("\n}\n", start) + 3]
            break
    assert body is not None
    assert "{ 0x84AB8CA8, sub_84AB8CA8 }" in (generated / "ch2k8_init.cpp").read_text()
    source = tmp_path / "script_callback.cpp"
    executable = tmp_path / "script_callback.exe"
    source.write_text(
        '#include "ch2k8_pch.h"\n#include <windows.h>\nstatic uint64_t observed;\n'
        'extern "C" void sub_8497AA48(PPCContext& ctx, uint8_t*) { observed = ctx.r3.u64; ctx.r3.u64 = 0xCAFE; }\n'
        + body + "\nint main() { PPCContext ctx{};\n"
        "auto memory = static_cast<uint8_t*>(VirtualAlloc(nullptr, 1ull << 32, MEM_RESERVE, PAGE_NOACCESS));\n"
        "if (!memory) return 2;\n"
        "if (!VirtualAlloc(memory + 0x8586E000u, 4096, MEM_COMMIT, PAGE_READWRITE)) return 3;\n"
        "const uint32_t values[] = {0, 0x12345678, 0xF2345678};\n"
        "for (uint32_t value : values) {\n"
        "*reinterpret_cast<uint32_t*>(memory + 0x8586E310u) = __builtin_bswap32(value);\n"
        "ctx.r3.u64 = 0xFFFFFFFFFFFFFFFFULL; ctx.lr = 0x12345678; ctx.r4.u64 = 0xAABB;\n"
        "sub_84AB8CA8(ctx, memory);\n"
        "assert(observed == value && ctx.r3.u64 == 0xCAFE && ctx.lr == 0x12345678 && ctx.r4.u64 == 0xAABB);\n"
        "}\nVirtualFree(memory, 0, MEM_RELEASE);\n}\n", encoding="utf-8",
    )
    compilation = subprocess.run(
        [compiler, "-std=c++23", "-O2", "-msse4.1", "-DNOMINMAX", "-DWIN32_LEAN_AND_MEAN",
         "-DSPDLOG_FMT_EXTERNAL", "-DSPDLOG_COMPILED_LIB", "-I", str(sdk), "-I", str(generated),
         str(source), "-o", str(executable)], capture_output=True, text=True,
    )
    assert compilation.returncode == 0, compilation.stderr
    execution = subprocess.run([str(executable)], capture_output=True, text=True)
    assert execution.returncode == 0, f"Script callback failed: {execution.returncode}, {execution.stderr}"


@pytest.mark.parametrize("address,field", [(0x84CA8998, 0x8565CE8C), (0x84CA8B60, 0x8565CE90)])
def test_generated_settings_getter_loads_stored_field(tmp_path, address, field):
    root = Path(__file__).resolve().parents[1]
    generated = root / "port/generated/default"
    sdk = root / "port/sdk/include"
    compiler = shutil.which("clang++")
    if sys.platform != "win32" or not compiler or not sdk.is_dir() or not generated.is_dir():
        pytest.skip("Requires Windows, local ReXGlue SDK, generated game code, and clang++")
    signature = f"DEFINE_REX_FUNC(sub_{address:08X}) {{"
    body = None
    for path in generated.glob("*_recomp.*.cpp"):
        text = path.read_text(encoding="utf-8")
        if signature in text:
            start = text.index(signature)
            body = text[start:text.index("\n}\n", start) + 3]
            break
    assert body is not None
    assert f"{{ 0x{address:08X}, sub_{address:08X} }}" in (generated / "ch2k8_init.cpp").read_text()
    source = tmp_path / "settings_getter.cpp"
    executable = tmp_path / "settings_getter.exe"
    source.write_text(
        '#include "ch2k8_pch.h"\n#include <windows.h>\n'
        + body + "\nint main() { PPCContext ctx{};\n"
        "auto memory = static_cast<uint8_t*>(VirtualAlloc(nullptr, 1ull << 32, MEM_RESERVE, PAGE_NOACCESS));\n"
        "if (!memory) return 2;\n"
        "if (!VirtualAlloc(memory + 0x8565C000u, 4096, MEM_COMMIT, PAGE_READWRITE)) return 3;\n"
        "const uint32_t values[] = {0, 0x12345678, 0xF2345678};\n"
        "for (uint32_t value : values) {\n"
        f"*reinterpret_cast<uint32_t*>(memory + 0x{field:08X}u) = __builtin_bswap32(value);\n"
        "ctx.r3.u64 = 0xFFFFFFFFFFFFFFFFULL; ctx.lr = 0x12345678; ctx.r4.u64 = 0xAABB;\n"
        f"sub_{address:08X}(ctx, memory);\n"
        "assert(ctx.r3.u64 == value && ctx.lr == 0x12345678 && ctx.r4.u64 == 0xAABB);\n"
        "}\nVirtualFree(memory, 0, MEM_RELEASE);\n}\n", encoding="utf-8",
    )
    compilation = subprocess.run(
        [compiler, "-std=c++23", "-O2", "-msse4.1", "-DNOMINMAX", "-DWIN32_LEAN_AND_MEAN",
         "-DSPDLOG_FMT_EXTERNAL", "-DSPDLOG_COMPILED_LIB", "-I", str(sdk), "-I", str(generated),
         str(source), "-o", str(executable)], capture_output=True, text=True,
    )
    assert compilation.returncode == 0, compilation.stderr
    execution = subprocess.run([str(executable)], capture_output=True, text=True)
    assert execution.returncode == 0, f"Settings getter failed: {execution.returncode}, {execution.stderr}"
