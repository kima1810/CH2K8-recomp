"""Hoist proved RAM-store eligibility outside the geometry kernel.

The original descriptor load and span query stay in place. Failed stack guards
jump to the corresponding point in an otherwise unchanged byte-store tail,
retaining the already-loaded register value and all earlier guest writes.
"""
import re
from prove_vector_store_ranges import prove_guarded_store_span


def hoist_ram_stores(body, proof, original_body=None):
    prepare = re.search(r'\tnative_span = native_ram\.PrepareSpan\([^\n]+\);\n', body)
    if not proof or not prepare:
        return body
    prefix = body[:prepare.end()]
    tail = body[prepare.end():]
    pattern = (r'if \(native_span\) native_ram.StorePrepared\(base, ea, ctx\.(v\d+)\); '
               r'else \{ Ch2k8StoreVectorLeft\(base, ea, ctx\.\1\); \+\+native_ram.counts\[1\]; \}')
    if len(re.findall(pattern, tail)) != proof['sites']:
        raise ValueError('Unexpected proved RAM store shape')
    native = re.sub(pattern,r'native_ram.StorePreparedDirect(base, ea, ctx.\1);',tail)
    fallback = re.sub(pattern,r'Ch2k8StoreVectorLeft(base, ea, ctx.\1); ++native_ram.counts[1];',tail)
    for index, guard in enumerate(proof['guards']):
        register=guard['register']
        check=(f'\tnative_span = native_span && ctx.r{register}.u64 <= '
               f'{guard["maximum"]}u && !(ctx.r{register}.u32 & 3u);')
        needle=guard['load']+'\n'+check
        if native.count(needle)!=1 or fallback.count(needle)!=1:
            raise ValueError('Unexpected guarded reload shape')
        native=native.replace(needle,guard['load']+'\n'+
            f'\tif (ctx.r{register}.u64 > {guard["maximum"]}u || '
            f'(ctx.r{register}.u32 & 3u)) goto native_fallback_guard_{index};')
        fallback=fallback.replace(needle,guard['load']+f'\nnative_fallback_guard_{index}:')
    # Prove the palette reads against the same output span by adding synthetic
    # accesses to the existing range/alignment analysis. No source is assumed
    # stable and no access is moved; only physical-address adaptation is shared.
    palette=re.compile(r'(\t// lvlx(?:128)? (v\d+),r11,r(\d+)\n)(\ttemp.u32 = ctx.r11.u32 \+ ctx.r\3.u32;\n)')
    original_body=original_body or body
    annotated=palette.sub(lambda m:f'\t// stvlx {m[2]},r11,r{m[3]}\n\tea = ctx.r11.u32 + ctx.r{m[3]}.u32;\n'+m[0],original_body)
    reads=len(palette.findall(original_body))
    combined=prove_guarded_store_span(annotated) if reads else None
    if combined and combined['span']<=proof['span'] and combined['sites']==proof['sites']+reads:
        native=palette.sub(lambda m:m[0]+'\t// CH2K8 proved palette address\n',native)
        native=re.sub(r'(\t// CH2K8 proved palette address\n\t[^\n]*?)REX_RAW_ADDR\(temp.u32 & ~0xF\)',
                      r'\1native_ram.PreparedAddress(temp.u32 & ~0xFu)',native)
    fallback=re.sub(r'\bloc_([0-9A-F]+)\b',r'native_fallback_loc_\1',fallback)
    if not native.endswith('\n}\n'):
        raise ValueError('Missing geometry function terminator')
    return (prefix+'\tif (!native_span) goto native_fallback_entry;\n'+
            native[:-3]+'\n\nnative_fallback_entry:\n'+fallback)
