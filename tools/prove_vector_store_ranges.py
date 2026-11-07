"""Conservative unsigned range/alignment proof for straight guest register code.

Unrecognized operations become unknown. Backedges widen increasing bounds to
unknown. Nothing is inferred from observed game data or assumed index values.
"""
import re
from collections import deque

TOP=(1<<64)-1
WRITE = r'\s*(?:(?:<<|>>|[+\-*/%&|^])?=(?!=)|\+\+|--)'


def trailing(value):
    return (value & -value).bit_length()-1 if value else 64


def transfer(line, state):
    match=re.match(r'\s*ctx\.r(\d+)\.(u64|s64|u32|s32) = (.*);$',line)
    if not match:
        partial=re.search(r'ctx\.r(\d+)\.\w+'+WRITE,line)
        if partial:
            out=list(state);out[int(partial[1])]=(TOP,0);return out
        if re.match(r'\s*\w+\(ctx, base\);$',line):
            return [(TOP,0)]*32
        return state
    destination, kind, expression=match.groups();destination=int(destination)
    result=(TOP,0)
    load=re.match(r'REX_LOAD_U(8|16|32)\(',expression)
    masked=re.search(r' & (0x[0-9A-Fa-f]+)$',expression)
    rotate=re.match(r'__builtin_rotateleft64\(ctx\.r(\d+)\.u32 \| \(ctx\.r\1\.u64 << 32\), (\d+)\) & (0x[0-9A-Fa-f]+)$',expression)
    copy=re.fullmatch(r'ctx\.r(\d+)\.(u64|u32)',expression)
    addition=re.fullmatch(r'ctx\.r(\d+)\.u64 \+ ctx\.r(\d+)\.u64',expression)
    add_constant=re.fullmatch(r'ctx\.r(\d+)\.(?:u64|s64) \+ (-?\d+)',expression)
    if load:
        result=((1<<int(load[1]))-1,0)
    elif rotate:
        source,shift,mask=int(rotate[1]),int(rotate[2]),int(rotate[3],16)
        maximum=min(state[source][0],0xFFFFFFFF)
        if 0<shift<32 and maximum < (1<<(32-shift)):
            result=(min(maximum<<shift,mask),max(trailing(mask),min(64,state[source][1]+shift)))
        else:
            result=(mask,trailing(mask))
    elif masked:
        mask=int(masked[1],16)
        result=(mask,trailing(mask))
    elif addition:
        left,right=state[int(addition[1])],state[int(addition[2])]
        result=(left[0]+right[0] if left[0]<=TOP-right[0] else TOP,min(left[1],right[1]))
    elif add_constant:
        source=state[int(add_constant[1])];value=int(add_constant[2])
        result=(source[0]+value if value>=0 and source[0]<=TOP-value else TOP,
                min(source[1],trailing(value & TOP)))
    elif copy:
        source=state[int(copy[1])]
        result=(min(source[0],0xFFFFFFFF) if copy[2]=='u32' else source[0],source[1])
    elif re.fullmatch(r'-?\d+',expression):
        value=int(expression)&TOP;result=(value,trailing(value))
    if kind in ('u32','s32'):
        # A subregister assignment does not establish the high 32 bits.
        result=(TOP,min(32,result[1]))
    out=list(state);out[destination]=result
    return out


def prove_store_span(body, *, _checked_loads=None):
    lines=body.splitlines()
    if re.search(r'\bswitch\b|\bwhile\s*\(|__try|REX_CALL_',body):return None
    for i,line in enumerate(lines):
        if line.strip().startswith('//'):continue
        if re.search(r'\bgoto\b',line) and not re.search(r'goto loc_[0-9A-F]+;',line):return None
        # Generated branches are explicit gotos. Do not infer unconditional
        # register facts through unfamiliar structured C++ conditionals.
        if re.match(r'\s*if\b',line) and not line.rstrip().endswith(';'):return None
        if re.match(r'\s*else\b',line):return None
        if re.search(r'\b(?:for|do)\b',line):
            # The generator's byte-store loop changes no guest registers.
            if line.strip() != 'for (size_t i = 0; i < (16 - (ea & 0xF)); i++)':
                return None
            if i+1>=len(lines) or not re.fullmatch(
                    r'\s*REX_STORE_U8\(ea \+ i, ctx\.v\d+\.u8\[15 - i\]\);',lines[i+1]):
                return None
    # All stores must use the same stable output base, loaded exactly once.
    stores={}
    for i,line in enumerate(lines):
        if line.strip().startswith('// stvlx '):
            if i+1>=len(lines): return None
            ea=re.fullmatch(r'\s*ea = ctx\.r11\.u32 \+ ctx\.r(\d+)\.u32;',lines[i+1])
            if not ea:return None
            stores[i+1]=int(ea[1])
    if not stores:return None
    if re.search(r'(?:\+\+|--)\s*ctx\.r\d+\.',body):return None
    base_writes=[line for line in lines if re.search(r'ctx\.r11\.\w+'+WRITE,line)]
    if base_writes != ['\tctx.r11.u64 = REX_LOAD_U32(ctx.r3.u32 + 116);']:
        return None
    loaded=next(i for i,line in enumerate(lines) if line==base_writes[0])
    if any(re.match(r'\s*\w+\(ctx, base\);$',line) for line in lines[loaded+1:max(stores)+1]):
        return None
    labels={line[:-1]:i for i,line in enumerate(lines) if re.fullmatch(r'loc_[0-9A-F]+:',line)}
    incoming={0:[(TOP,0)]*32};queue=deque([0]);observed={}
    while queue:
        i=queue.popleft();state=incoming[i]
        if i in stores:
            bound,alignment=state[stores[i]]
            if bound>0xFFFFFFFF or alignment<2:return None
            observed[i]=max(observed.get(i,0),bound)
        line=lines[i]
        outgoing=transfer(line,state)
        if _checked_loads and i in _checked_loads:
            register,bound,alignment=_checked_loads[i]
            outgoing=list(outgoing)
            outgoing[register]=(bound,alignment)
        branch=re.search(r'goto (loc_[0-9A-F]+);',line)
        edges=[]
        if branch:
            if branch[1] not in labels:return None
            edges.append(labels[branch[1]])
        if not line.strip().startswith(('return;','goto ')) and i+1<len(lines):
            edges.append(i+1)
        for target in edges:
            if target not in incoming:
                incoming[target]=outgoing;queue.append(target);continue
            old=incoming[target];merged=[]
            for before,after in zip(old,outgoing):
                maximum=max(before[0],after[0]);alignment=min(before[1],after[1])
                if target<=i and maximum>before[0]:maximum=TOP
                merged.append((maximum,alignment))
            if merged!=old:incoming[target]=merged;queue.append(target)
    if len(observed)!=len(stores):return None
    maximum=max(observed.values())
    if maximum>0x1000000:return None
    # Every partial stvlx ends at its 16-byte block boundary.
    span=(maximum+16+15)&~15
    return {'span':span,'maximum_offset':maximum,'sites':len(stores)}


def prove_guarded_store_span(body):
    """Conditional proof: exact stack-to-store reloads need emitted checks.

    No stored stack value is assumed stable. The guard checks the value after
    its original volatile load, and permanently disables widening on failure.
    """
    unguarded=prove_store_span(body)
    if unguarded:
        return {**unguarded, 'guards': []}
    lines=body.splitlines(); checked={}; guards=[]
    base_load='\tctx.r11.u64 = REX_LOAD_U32(ctx.r3.u32 + 116);'
    if lines.count(base_load)!=1:return None
    loaded=lines.index(base_load)
    labels={line[:-1]:i for i,line in enumerate(lines) if re.fullmatch(r'loc_[0-9A-F]+:',line)}
    for i,line in enumerate(lines):
        branch=re.search(r'goto (loc_[0-9A-F]+);',line)
        # A failed check must not be followed by another span initialization.
        if branch and i>loaded and labels.get(branch[1],loaded)<=loaded:return None
    # Eligibility window only: larger legal stack offsets retain byte stores.
    limit=40944
    for i,line in enumerate(lines):
        match=re.fullmatch(r'\s*ctx\.r(\d+)\.u64 = REX_LOAD_U32\(ctx\.r1\.u32 \+ (-?\d+)\);',line)
        if not match or i<=loaded or i+2>=len(lines):continue
        register=int(match[1])
        if not re.fullmatch(r'\s*// stvlx v\d+,r11,r'+str(register),lines[i+1]):continue
        if lines[i+2].strip()!=f'ea = ctx.r11.u32 + ctx.r{register}.u32;':continue
        checked[i]=(register,limit,2)
        guards.append({'load':line,'register':register,'maximum':limit})
    if not guards:return None
    proof=prove_store_span(body,_checked_loads=checked)
    return {**proof,'guards':guards} if proof else None
