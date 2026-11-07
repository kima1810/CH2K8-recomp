"""Share physical-alias adaptation for the two checked 48-byte input loops."""
import re


def adapt_input_stream(native, original, address):
    labels={'84723778':'847237E8','84723CC0':'84723D60'}
    if address not in labels:return native,0
    label=labels[address]
    if (original.count('ctx.r10.s64 = ctx.r10.s64 + 48;')!=1 or
        original.count('ctx.r5.s64 = ctx.r5.s64 + -1;')!=1 or
        original.count('goto loc_'+label+';')!=1 or
        original.count('loc_'+label+':')!=1):
        raise ValueError('Unrecognized bounded input loop')
    # These exact count emissions precede the loop and bound the iteration count
    # to 8191. A zero count still executes the original do/while body once.
    counts={
      '84723778':'ctx.r5.u64 = __builtin_rotateleft64(ctx.r9.u32 | (ctx.r9.u64 << 32), 29) & 0x1FFFFFFF;',
      '84723CC0':'ctx.r5.u64 = ctx.r8.u32 & 0x1FFF;'}
    if counts[address] not in original[:original.index('loc_'+label+':')]:
        raise ValueError('Unrecognized input iteration count')
    loop=original[original.index('loc_'+label+':'):]
    back=loop.index('goto loc_'+label+';')
    loop=loop[:back+len('goto loc_'+label+';')]
    for register in (5,10):
        writes=re.findall(r'\s*(ctx.r'+str(register)+r'\.\w+ = [^\n]+;)',loop)
        expected=f'ctx.r{register}.s64 = ctx.r{register}.s64 + '+('-1;' if register==5 else '48;')
        if writes!=[expected]:raise ValueError('Input loop register modified unexpectedly')
    if ('ctx.cr6.compare<int32_t>(ctx.r5.s32, 0, ctx.xer);' not in loop or
        f'if (ctx.cr6.gt) goto loc_{label};' not in loop or
        re.search(r'\t\w+\(ctx, base\);',loop) or
        re.findall(r'goto (loc_[0-9A-F]+);',loop)!=['loc_'+label] or
        not re.search(r'// bgt cr6,0x'+label.lower()+r'\n\tif \(ctx.cr6.gt\) goto loc_'+label+r';',loop)):
        raise ValueError('Unrecognized input loop control')
    compare='ctx.cr6.compare<int32_t>(ctx.r5.s32, 0, ctx.xer);'
    if re.findall(r'ctx.cr6.\w+',loop[loop.index(compare)+len(compare):])!=['ctx.cr6.gt']:
        raise ValueError('Input loop condition modified before its backedge')
    relative={10:0};changes=[]
    tail=original[original.index('loc_'+label+':')+len('loc_'+label+':'):]
    for op in re.finditer(r'\t// ([^\n]+)\n(.*?)(?=\t// |\nloc_|\n\}|$)',tail,re.S):
        code=op[2]
        load=re.search(r'REX_LOAD_U32\(ctx.r(\d+).u32 \+ (-?\d+)\)',code)
        vector=re.fullmatch(r'lvx(?:128)? v\d+,r0,r(\d+)',op[1])
        replacement=op[0]
        if load and int(load[1]) in relative:
            offset=relative[int(load[1])]+int(load[2])
            if not 0<=offset<=44:raise ValueError('Input load escaped its record')
            ea=f'ctx.r{load[1]}.u32 + {load[2]}'
            replacement=replacement.replace(load[0],
                f'__builtin_bswap32(*reinterpret_cast<volatile uint32_t*>(input_span.Address(uint32_t({ea}))))')
        if vector and int(vector[1]) in relative:
            if not 0<=relative[int(vector[1])]<=32:raise ValueError('Input vector escaped its record')
            if 'REX_RAW_ADDR(ea)' not in code:raise ValueError('Unrecognized input vector load')
            replacement=replacement.replace('REX_RAW_ADDR(ea)','input_span.Address(ea)')
        if replacement!=op[0]:changes.append((op[0],replacement))
        # Only exact scalar address copies are propagated. All other writes,
        # including partial writes and helper calls, invalidate the relation.
        for line in code.splitlines():
            write=re.search(r'ctx.r(\d+)\.\w+\s*(?:[+*/&|^-]?=|<<=|>>=)',line)
            if write:
                dst=int(write[1]);value=None
                add=re.fullmatch(r'\s*ctx.r\d+\.(?:s64|u64) = ctx.r(\d+)\.(?:s64|u64) \+ (-?\d+);',line)
                if add and int(add[1]) in relative:value=relative[int(add[1])]+int(add[2])
                relative.pop(dst,None)
                if value is not None:relative[dst]=value
            if re.match(r'\s*\w+\(ctx, base\);',line):relative.clear()
    for old,new in changes:
        if native.count(old)!=1:raise ValueError('Ambiguous input instruction')
        native=native.replace(old,new,1)
    gate=(f'\tif (!input_span.Prepare(base,ctx.r10.u32,\n'
          f'\t    uint64_t(ctx.r5.u32?ctx.r5.u32:1)*48)) goto native_fallback_loc_{label};\n')
    native=native.replace('loc_'+label+':',gate+'loc_'+label+':',1)
    return native,len(changes)
