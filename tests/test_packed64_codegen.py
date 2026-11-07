"""Compare the pinned SDK correction with Xenia's SIMD unpack sequence.

The oracle is adapted from Xenia (Copyright (c) 2015, Ben Vanik).
See XENIA_LICENSE.txt for its BSD license and disclaimer.
"""
import shutil
import re
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from fix_codegen import correct_packed64_unpack, correct_packed64_pack


def emitted_pack(dst='v0', src='v0', shift=0):
    lines = [f'\t// vpkd3d128 {dst},{src},6,2,{shift}', '\tvTemp.u64[0] = 0;']
    for lane in range(4):
        lines.append(f'\ttemp.s32 = int32_t(ctx.{src}.f32[{lane}]);')
        if lane == 0:
            lines.append('\tvTemp.u64[0] = uint64_t(temp.s32 & 0xFFFFF);')
        else:
            mask = '0xF' if lane == 3 else '0xFFFFF'
            lines.append(f'\tvTemp.u64[0] |= uint64_t(temp.s32 & {mask}) << {20*lane};')
    return '\n'.join(lines + [f'\tctx.{dst}.u64[{shift//2}] = vTemp.u64[0];'])


def emitted_block(dst='v0', src='v0'):
    lines = [f'\t// vupkd3d128 {dst},{src},24', f'\tvTemp.u64[0] = ctx.{src}.u64[1];']
    for lane, shift in enumerate((44, 24, 4)):
        lines += [f'\ttemp.s32 = (int32_t(vTemp.u64[0] << {shift}) >> 44);',
                  f'\tctx.{dst}.f32[{lane}] = float(temp.s32);']
    return '\n'.join(lines + [f'\tctx.{dst}.f32[3] = float(vTemp.u64[0] >> 60);'])


def test_packed64_correction_is_exact_and_idempotent():
    raw = emitted_block()
    corrected, count = correct_packed64_unpack(raw)
    assert count == 1
    assert correct_packed64_unpack(corrected) == (corrected, 0)
    assert correct_packed64_unpack(raw.replace(',24', ',20')) == (raw.replace(',24', ',20'), 0)
    # Unexpected generator shapes must not be silently rewritten.
    unexpected = raw.replace('float(temp.s32)', 'double(temp.s32)', 1)
    assert correct_packed64_unpack(unexpected) == (unexpected, 0)
    for shift in (0, 2):
        corrected, count = correct_packed64_pack(emitted_pack(shift=shift))
        assert count == 1
        assert correct_packed64_pack(corrected) == (corrected, 0)


def test_local_generated_packed64_sites_match_correction():
    generated = Path(__file__).resolve().parents[1] / 'port/generated/default'
    if not generated.is_dir():
        pytest.skip('Requires locally generated game code')
    count = 0
    packs = 0
    duplicated_unpacks = 0
    for path in generated.glob('*_recomp.*.cpp'):
        source = path.read_text()
        for duplicate in re.finditer(r'static void sub_[0-9A-F]{8}_fast\([^\n]+\) \{', source):
            end = source.index('\n}\n', duplicate.start())
            duplicated_unpacks += len(re.findall(r'\t// vupkd3d128 (v\d+),(v\d+),24\n', source[duplicate.start():end]))
        for match in re.finditer(r'\t// vupkd3d128 (v\d+),(v\d+),24\n', source):
            expected, _ = correct_packed64_unpack(emitted_block(*match.groups()))
            assert source[match.start():].startswith(expected), path
            count += 1
        for match in re.finditer(r'\t// vpkd3d128 (v\d+),(v\d+),6,2,([02])\n', source):
            dst, src, shift = match.groups()
            expected, _ = correct_packed64_pack(emitted_pack(dst, src, int(shift)))
            assert source[match.start():].startswith(expected), path
            packs += 1
    assert count == 163 + duplicated_unpacks
    assert packs == 89


def test_packed64_matches_xenia_simd_oracle(tmp_path):
    compiler = shutil.which('clang++')
    if not compiler:
        pytest.skip('Requires clang++ and x86 SIMD')
    inplace, _ = correct_packed64_unpack(emitted_block())
    distinct, _ = correct_packed64_unpack(emitted_block('v1', 'v0'))
    pack_functions = ''
    for shift in (0, 2):
        for alias in (False, True):
            dst = 'v0' if alias else 'v1'
            code, _ = correct_packed64_pack(emitted_pack(dst, 'v0', shift))
            pack_functions += f'void pack{shift}_{int(alias)}(Context& ctx) {{ V vTemp{{}}; union {{ int32_t s32; uint32_t u32; float f32; }} temp{{}};\n{code}\n}}\n'
    source = tmp_path / 'packed64.cpp'
    executable = tmp_path / ('packed64.exe' if sys.platform == 'win32' else 'packed64')
    source.write_text(r'''
#include <immintrin.h>
#include <cstdint>
#include <cassert>
union alignas(16) V { uint64_t u64[2]; uint32_t u32[4]; float f32[4]; };
struct Context { V v0, v1; };
void inplace(Context& ctx) { V vTemp{}; union { int32_t s32; } temp{};
''' + inplace + r'''
}
void distinct(Context& ctx) { V vTemp{}; union { int32_t s32; } temp{};
''' + distinct + '\n}\n' + pack_functions + r'''
// Independent spelling of Xenia's EmitULONG_4202020 SIMD sequence and constants
// (BSD-3-Clause), src/xenia/cpu/backend/x64/{x64_seq_vector,x64_emitter}.cc.
// Xenia stores guest words forward; ReXGlue stores them in reverse order.
V oracle(V input) {
    auto v = _mm_set_epi32(input.u32[0], input.u32[1], input.u32[2], input.u32[3]);
    v = _mm_shuffle_epi8(v, _mm_set_epi32(0xFFFFFF0B, 0xFF080F0E, 0xFF0B0A09, 0xFF0E0D0C));
    auto shifted = _mm_srli_epi32(v, 4);
    auto f = _mm_shuffle_ps(_mm_castsi128_ps(v), _mm_castsi128_ps(shifted), _MM_SHUFFLE(3,2,1,0));
    f = _mm_shuffle_ps(f, f, _MM_SHUFFLE(3,1,2,0));
    v = _mm_srai_epi32(_mm_slli_epi32(_mm_castps_si128(f), 12), 12);
    v = _mm_add_epi32(v, _mm_set_epi32(0x3F800000, 0x40400000, 0x40400000, 0x40400000));
    auto overflow = _mm_castps_si128(_mm_cmpeq_ps(_mm_castsi128_ps(v), _mm_castsi128_ps(_mm_set1_epi32(0x40380000))));
    v = _mm_blendv_epi8(v, _mm_set1_epi32(0x7FC00000), overflow);
    v = _mm_shuffle_epi32(v, _MM_SHUFFLE(0,1,2,3));
    V result; _mm_store_si128(reinterpret_cast<__m128i*>(&result), v); return result;
}
uint64_t pack_oracle(V input) {
    auto v = _mm_castsi128_ps(_mm_set_epi32(input.u32[0], input.u32[1], input.u32[2], input.u32[3]));
    v = _mm_max_ps(v, _mm_castsi128_ps(_mm_set_epi32(0x40400000,0x40380001,0x40380001,0x40380001)));
    v = _mm_min_ps(v, _mm_castsi128_ps(_mm_set_epi32(0x4040000F,0x4047FFFF,0x4047FFFF,0x4047FFFF)));
    auto bits = _mm_and_si128(_mm_castps_si128(v), _mm_set_epi32(0xF,0xFFFFF,0xFFFFF,0xFFFFF));
    auto shifted = _mm_slli_epi32(bits,4);
    auto xz = _mm_shuffle_epi8(bits,_mm_set_epi32(0xFF020100,0x0A0908FF,0xFFFFFFFF,0xFFFFFFFF));
    auto yw = _mm_shuffle_epi8(shifted,_mm_set_epi32(0x0504FFFF,0x0CFFFF06,0xFFFFFFFF,0xFFFFFFFF));
    V packed; _mm_store_si128(reinterpret_cast<__m128i*>(&packed),_mm_or_si128(xz,yw));
    return (uint64_t(packed.u32[2])<<32) | packed.u32[3];
}
void check_pack(V input) {
    uint64_t expected=pack_oracle(input);
    Context ctx; ctx.v0=input; ctx.v1.u64[0]=0xAABB; ctx.v1.u64[1]=0xCCDD;
    pack0_0(ctx); assert(ctx.v1.u64[0]==expected && ctx.v1.u64[1]==0xCCDD);
    pack2_0(ctx); assert(ctx.v1.u64[1]==expected && ctx.v1.u64[0]==expected);
    for(int i=0;i<4;++i) assert(ctx.v0.u32[i]==input.u32[i]);
    pack0_1(ctx); assert(ctx.v0.u64[0]==expected && ctx.v0.u64[1]==input.u64[1]);
    ctx.v0=input; pack2_1(ctx); assert(ctx.v0.u64[1]==expected && ctx.v0.u64[0]==input.u64[0]);
}
void check(uint64_t packed, uint64_t other) {
    Context ctx{}; ctx.v0.u64[0] = packed; ctx.v0.u64[1] = other;
    V expected = oracle(ctx.v0), original = ctx.v0;
    check_pack(expected); check_pack(original);
    distinct(ctx);
    for(int i=0;i<4;++i) { assert(ctx.v1.u32[i] == expected.u32[i]); assert(ctx.v0.u32[i] == original.u32[i]); }
    inplace(ctx);
    for(int i=0;i<4;++i) assert(ctx.v0.u32[i] == expected.u32[i]);
}
int main() {
    const uint32_t special[] = {0,0x80000000,0x3F800000,0x40380000,0x40380001,0x40400000,0x4047FFFF,0x40480000,0x7F800000,0xFF800000,0x7FC00000,0x7F800001};
    for(auto a:special) for(auto b:special) { V v; v.u32[0]=a; v.u32[1]=b; v.u32[2]=a; v.u32[3]=b; check_pack(v); }
    Context zero{}; inplace(zero);
    assert(zero.v0.u32[3] == 0x40400000 && zero.v0.u32[2] == 0x40400000);
    assert(zero.v0.u32[1] == 0x40400000 && zero.v0.u32[0] == 0x3F800000);
    const uint32_t edges[] = {0,1,0x7FFFF,0x80000,0x80001,0xFFFFF};
    for(auto x:edges) for(auto y:edges) for(auto z:edges) for(uint64_t w=0;w<16;++w)
        check(uint64_t(x) | (uint64_t(y)<<20) | (uint64_t(z)<<40) | (w<<60), 0x123456789ABCDEF0);
    uint64_t state = 0x123456789ABCDEF0;
    for(int i=0;i<10000;++i) { state ^= state<<13; state ^= state>>7; state ^= state<<17; check(state, ~state); }
}
''', encoding='utf-8')
    compilation = subprocess.run([compiler, '-std=c++23', '-O2', '-msse4.1', str(source), '-o', str(executable)], capture_output=True, text=True)
    assert compilation.returncode == 0, compilation.stderr
    execution = subprocess.run([str(executable)], capture_output=True, text=True)
    assert execution.returncode == 0, execution.stderr
