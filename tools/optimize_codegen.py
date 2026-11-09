"""Add optional, paired-testable pack fast paths to three measured hot routines.

Only recognizes the complete already-corrected type-6 emission; never rewrites
other instructions or hand-edits generated sources. Generated duplicates stay
local. Unknown generator shapes fail rather than silently losing coverage.
"""
import re
import hashlib
from pathlib import Path
from geometry_batch_codegen import batch_normalization
from geometry_ram_codegen import hoist_ram_stores
from geometry_input_codegen import adapt_input_stream
from prove_vector_store_ranges import prove_guarded_store_span

TARGETS = ('84723778', '84723CC0', '84724930')
# Audited corrected baseline bodies from the pinned SDK. The newer scheduling
# and shared-address proofs deliberately reject changes elsewhere in a kernel.
GEOMETRY_BODIES = {
    '84723778': '3830523667cd38c371db28cf05a75932f205fdf6f606b30aa98caacf64137b81',
    '84723CC0': 'b0a2ae762a194988b5027969b6ae001c608ff8286ce5c8a3156da722ffadf5cb',
    '84724930': '87227d31ecafc6932a9c3e38b30723e513e99373795dc5aa6506d08b652664ee',
}
OLD_MARKER = '// CH2K8 measured packed-vector variants'
V2_MARKER = OLD_MARKER + ' v2'
V3_MARKER = OLD_MARKER + ' v3'
V4_MARKER = OLD_MARKER + ' v4'
MARKER = OLD_MARKER + ' v5'


def scalar_pack(dst, src, half):
    lines = [f'\t// vpkd3d128 {dst},{src},6,2,{half*2}', '\tvTemp.u64[0] = 0;']
    for component, lane in enumerate((3, 2, 1, 0)):
        minimum = '0x40380001u' if component < 3 else '0x40400000u'
        maximum = '0x4047FFFFu' if component < 3 else '0x4040000Fu'
        mask = '0xFFFFFu' if component < 3 else '0xFu'
        lines += [f'\ttemp.u32 = ctx.{src}.u32[{lane}];',
                  f'\tvTemp.u32[2] = {minimum};',
                  '\tif (!(temp.f32 >= vTemp.f32[2])) temp.u32 = vTemp.u32[2];',
                  f'\tvTemp.u32[2] = {maximum};',
                  '\tif (temp.f32 > vTemp.f32[2]) temp.u32 = vTemp.u32[2];',
                  f'\tvTemp.u64[0] |= uint64_t(temp.u32 & {mask}) << {component*20};']
    lines.append(f'\tctx.{dst}.u64[{half}] = vTemp.u64[0];')
    return '\n'.join(lines)


def scalar_unpack(dst, src):
    lines = [f'\t// vupkd3d128 {dst},{src},24', f'\tvTemp.u64[0] = ctx.{src}.u64[0];']
    for lane, shift in zip((3, 2, 1), (44, 24, 4)):
        lines += [f'\ttemp.s32 = (int64_t(vTemp.u64[0] << {shift}) >> 44);',
                  f'\tctx.{dst}.u32[{lane}] = temp.s32 == -524288 ? 0x7FC00000u : uint32_t(temp.s32 + 0x40400000);']
    lines.append(f'\tctx.{dst}.u32[0] = uint32_t(vTemp.u64[0] >> 60) + 0x3F800000u;')
    return '\n'.join(lines)


def vectorize_small_unpack(body):
    """Replace the exact scalar color and 10:10:10:2 decode emissions."""
    for dst, src, kind in re.findall(r'\t// vupkd3d128 (v\d+),(v\d+),([08])\n', body):
        lines = [f'\t// vupkd3d128 {dst},{src},{kind}']
        if kind == '0':
            lines += [f'\tvTemp.u32[{lane}] = ctx.{src}.u8[{byte}] | 0x3F800000;'
                      for lane, byte in enumerate((3, 0, 1, 2))]
            lines.append(f'\tctx.{dst} = vTemp;')
            call = f'Ch2k8UnpackColor(ctx.{dst}, ctx.{src}, vTemp);'
        else:
            for lane, shift in ((3, 22), (2, 12), (1, 2)):
                value = ('temp.s32 == -512 ? 0x7FC00000 : (temp.s32 + 0x40400000)'
                         if lane == 3 else 'temp.s32 + 0x40400000')
                lines += [f'\ttemp.s32 = (ctx.{src}.s32[0] << {shift}) >> 22;',
                          f'\tvTemp.s32[0] = {value};',
                          f'\tctx.{dst}.u32[{lane}] = vTemp.u32[0];']
            lines += [f'\tvTemp.u32[0] = (ctx.{src}.u32[0] >> 30) | 0x3F800000;',
                      f'\tctx.{dst}.u32[0] = vTemp.u32[0];']
            call = f'Ch2k8UnpackBiased32(ctx.{dst}, ctx.{src}, temp, vTemp);'
        original = '\n'.join(lines) + '\n'
        if original not in body:
            raise ValueError(f'Unexpected geometry unpack emission: {lines[0]}')
        body = body.replace(original, lines[0]+'\n\t'+call+'\n', 1)
    return body


def dispatch(signature, address, index, version=5):
    if version == 1:
        return (signature + '\n' + f'\tif (Ch2k8SelectFastVectorPack({index})) {{\n'
                f'\t\tsub_{address}_fast(ctx, base);\n\t\treturn;\n\t}}\n'
                f'\tCh2k8HotScope hot({index}, ctx.r3.u32, base, false);\n')
    ram_dispatch = (f'\t\t\t\t\tif (Ch2k8SelectGeometryBatch({index})) {{\n'
                    f'\t\t\t\t\t\tif (Ch2k8HotProfilingEnabled()) sub_{address}_geometry_fast<true>(ctx, base);\n'
                    f'\t\t\t\t\t\telse sub_{address}_geometry_fast<false>(ctx, base);\n'
                    f'\t\t\t\t\t}} else {{\n'
                    f'\t\t\t\t\t\tsub_{address}_ram_fast(ctx, base);\n'
                    f'\t\t\t\t\t}}\n') if version >= 5 else f'\t\t\t\t\tsub_{address}_ram_fast(ctx, base);\n'
    native_dispatch = (f'\t\t\t\tif (Ch2k8SelectFastRamStore({index})) {{\n'
                       + ram_dispatch + '\t\t\t\t} else {\n'
                       f'\t\t\t\t\tsub_{address}_store_fast(ctx, base);\n\t\t\t\t}}\n') if version >= 4 else f'\t\t\t\tsub_{address}_store_fast(ctx, base);\n'
    store_dispatch = (f'\t\t\tif (Ch2k8SelectFastVectorStore({index})) {{\n'
                      + native_dispatch + '\t\t\t} else {\n'
                      f'\t\t\t\tsub_{address}_unpack_fast(ctx, base);\n\t\t\t}}\n') if version >= 3 else f'\t\t\tsub_{address}_unpack_fast(ctx, base);\n'
    return (signature + '\n' + f'\tif (Ch2k8SelectFastVectorPack({index})) {{\n'
            f'\t\tif (Ch2k8SelectFastVectorUnpack({index})) {{\n'
            + store_dispatch + '\t\t} else {\n'
            f'\t\t\tsub_{address}_fast(ctx, base);\n\t\t}}\n\t\treturn;\n\t}}\n'
            f'\tCh2k8HotScope hot({index}, ctx.r3.u32, base, false);\n')


def restore_source(text):
    if OLD_MARKER not in text:
        return text
    marker = text.splitlines()[0]
    if marker not in (OLD_MARKER, V2_MARKER, V3_MARKER, V4_MARKER, MARKER):
        raise ValueError('Unknown hot-function transform version')
    for index, address in enumerate(TARGETS):
        signature = f'DEFINE_REX_FUNC(sub_{address}) {{'
        if signature not in text:
            continue
        start = text.index(signature)
        end = text.index('\n}\n', start) + 3
        body = text[start:end]
        version = 5 if marker == MARKER else 4 if marker == V4_MARKER else 3 if marker == V3_MARKER else 2 if marker == V2_MARKER else 1
        expected = dispatch(signature, address, index, version)
        if not body.startswith(expected + '\tREX_FUNC_PROLOGUE();'):
            raise ValueError(f'{address}: unrecognized retained baseline dispatcher')
        text = text[:start] + signature + '\n' + body[len(expected):] + text[end:]
        for suffix in ('fast', 'unpack_fast', 'store_fast', 'ram_fast', 'geometry_fast'):
            pattern = (r'(?:template<bool Count>\n)?' + rf'static void sub_{address}_{suffix}\(PPCContext& __restrict ctx, '
                       r'uint8_t\* base\) \{\n.*?\n\}\n\n?')
            text, removed = re.subn(pattern, '', text, flags=re.S)
            required = suffix == 'fast' or (suffix == 'unpack_fast' and version >= 2) or (suffix == 'store_fast' and version >= 3) or (suffix == 'ram_fast' and version >= 4) or (suffix == 'geometry_fast' and version >= 5)
            if removed != int(required):
                raise ValueError(f'{address}: unexpected {suffix} copy count')
    includes = '\n#include "vector_store_optimized.h"' if marker in (V3_MARKER, V4_MARKER, MARKER) else ''
    return text.replace(marker+'\n#include "packed_vector_optimized.h"'+includes+'\n', '', 1)


def optimize_source(original_text):
    text = restore_source(original_text)
    total = 0
    for index, address in enumerate(TARGETS):
        signature = f'DEFINE_REX_FUNC(sub_{address}) {{'
        if signature not in text:
            continue
        start = text.index(signature)
        end = text.index('\n}\n', start) + 3
        body = text[start:end]
        optimized = body
        sites = re.findall(r'\t// vpkd3d128 (v\d+),(v\d+),6,2,([02])\n', body)
        if len(sites) != 16:
            raise ValueError(f'{address}: expected 16 verified pack sites, got {len(sites)}')
        for dst, src, shift in sites:
            half = int(shift)//2
            original = scalar_pack(dst, src, half)
            if optimized.count(original) != 1:
                raise ValueError(f'{address}: unexpected pack shape {dst}/{src}/{half}')
            replacement = (f'\t// vpkd3d128 {dst},{src},6,2,{shift} (integer SIMD)\n'
                           f'\tCh2k8PackBiased64(ctx.{dst}, ctx.{src}, temp, vTemp, {half});')
            optimized = optimized.replace(original, replacement, 1)
        unpacked = optimized
        unpack_sites = re.findall(r'\t// vupkd3d128 (v\d+),(v\d+),24\n', body)
        if not unpack_sites:
            raise ValueError(f'{address}: missing verified unpack sites')
        for dst, src in unpack_sites:
            scalar = scalar_unpack(dst, src)
            if unpacked.count(scalar) != 1:
                raise ValueError(f'{address}: unexpected unpack shape {dst}/{src}')
            unpacked = unpacked.replace(scalar,
                f'\t// vupkd3d128 {dst},{src},24 (integer SIMD)\n'
                f'\tCh2k8UnpackBiased64(ctx.{dst}, ctx.{src}, temp, vTemp);', 1)
        stored = unpacked
        store_pattern = (r'\t// stvlx (v\d+),([^\n]+)\n(\tea = [^\n]+;\n)'
                         r'\tfor \(size_t i = 0; i < \(16 - \(ea & 0xF\)\); i\+\+\)\n'
                         r'\t\tREX_STORE_U8\(ea \+ i, ctx\.\1\.u8\[15 - i\]\);')
        stored, store_count = re.subn(store_pattern, lambda m:
            f'\t// stvlx {m[1]},{m[2]} (aligned byte-store path)\n'+m[3]+
            f'\tCh2k8StoreVectorLeft(base, ea, ctx.{m[1]});', stored)
        if store_count != body.count('\t// stvlx '):
            raise ValueError(f'{address}: unexpected store shape')
        rammed = stored
        proof=prove_guarded_store_span(body)
        if proof or '// vrsqrtefp' in body:
            if hashlib.sha256(body.encode()).hexdigest() != GEOMETRY_BODIES[address]:
                raise ValueError(f'{address}: geometry kernel changed; re-audit required')
        if proof:
            rammed=re.sub(r'Ch2k8StoreVectorLeft\(base, ea, ctx\.(v\d+)\);',
                r'if (native_span) native_ram.StorePrepared(base, ea, ctx.\1); else { Ch2k8StoreVectorLeft(base, ea, ctx.\1); ++native_ram.counts[1]; }',rammed)
            load='\tctx.r11.u64 = REX_LOAD_U32(ctx.r3.u32 + 116);'
            assert rammed.count(load)==1
            rammed=rammed.replace(load,load+f'\n\tnative_span = native_ram.PrepareSpan(base, ctx.r11.u32, {proof["span"]}, &ctx, sizeof(ctx));',1)
            for guard in proof['guards']:
                if rammed.count(guard['load'])!=1:
                    raise ValueError(f'{address}: ambiguous guarded stack reload')
                register=guard['register']
                rammed=rammed.replace(guard['load'],guard['load']+
                    f'\n\tnative_span = native_span && ctx.r{register}.u64 <= {guard["maximum"]}u && !(ctx.r{register}.u32 & 3u);',1)
        geometry = hoist_ram_stores(rammed, proof, body)
        geometry, batch_groups = batch_normalization(geometry) if not proof else (geometry, 0)
        # The proof was established before duplicating the fallback tail. Batch
        # only the native tail, leaving the fallback's original FP order intact.
        if proof:
            split=geometry.index('\nnative_fallback_entry:')
            native, input_sites=adapt_input_stream(geometry[:split],body,address)
            native, batch_groups=batch_normalization(native+'\n}\n')
            geometry=native[:-3]+geometry[split:]
        geometry = vectorize_small_unpack(geometry)
        geometry = geometry.replace('native_ram.StorePreparedDirect(', 'native_ram.StorePreparedDirect<Count>(')
        geometry = geometry.replace('++native_ram.counts[1];', 'if constexpr(Count) ++native_ram.counts[1];')
        geometry = geometry.replace(signature,
            f'template<bool Count>\nstatic void sub_{address}_geometry_fast(PPCContext& __restrict ctx, uint8_t* base) {{\n'
            f'\tCh2k8LinearAddressSpan input_span;\n'
            f'\tCh2k8RamStoreScope native_ram(true);\n'
            f'\tbool native_span = false;\n'
            f'\tconstexpr bool native_batch = true;\n'
            f'\tCh2k8HotScope hot({index}, ctx.r3.u32, base, true, true, true, {str(bool(proof)).lower()}, native_ram.counts);',1)
        rammed = rammed.replace(signature,
            f'static void sub_{address}_ram_fast(PPCContext& __restrict ctx, uint8_t* base) {{\n'
            f'\tCh2k8RamStoreScope native_ram(true);\n'
            f'\tbool native_span = false;\n'
            f'\tCh2k8HotScope hot({index}, ctx.r3.u32, base, true, true, true, {str(bool(proof)).lower()}, native_ram.counts);', 1)
        stored = stored.replace(signature,
            f'static void sub_{address}_store_fast(PPCContext& __restrict ctx, uint8_t* base) {{\n'
            f'\tCh2k8HotScope hot({index}, ctx.r3.u32, base, true, true, true);', 1)
        unpacked = unpacked.replace(signature,
            f'static void sub_{address}_unpack_fast(PPCContext& __restrict ctx, uint8_t* base) {{\n'
            f'\tCh2k8HotScope hot({index}, ctx.r3.u32, base, true, true);', 1)
        optimized = optimized.replace(signature,
            f'static void sub_{address}_fast(PPCContext& __restrict ctx, uint8_t* base) {{\n'
            f'\tCh2k8HotScope hot({index}, ctx.r3.u32, base, true);', 1)
        baseline = body.replace(signature+'\n', dispatch(signature, address, index), 1)
        text = text[:start] + optimized + '\n' + unpacked + '\n' + stored + '\n' + rammed + '\n' + geometry + '\n' + baseline + text[end:]
        total += len(sites)
    if total:
        text = MARKER + '\n#include "packed_vector_optimized.h"\n#include "vector_store_optimized.h"\n' + text
    return text, total if text != original_text else 0


def optimize_directory(generated: Path):
    total = 0
    for path in sorted(generated.glob('*_recomp.*.cpp')):
        text = path.read_text(encoding='utf-8')
        if not any(f'DEFINE_REX_FUNC(sub_{a}) {{' in text for a in TARGETS):
            continue
        changed, count = optimize_source(text)
        if count:
            path.write_text(changed, encoding='utf-8', newline='\n')
            total += count
    return total
