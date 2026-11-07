"""Prove independent broadcast normalization operations can share four lanes.

Only moves exact recognized reciprocal-square-root emissions within straight
line, call-free arithmetic. Every source must have an unchanged broadcast DPPS
definition; moved destinations cannot cross another read or write of that value.
The original instruction positions remain available in the disabled path.
"""
import itertools
import re

RSQRT = re.compile(r'vrsqrtefp(?:128)? (v\d+),(v\d+)$')
PURE = re.compile(r'(?:v\w+|rlw\w+|clrl\w+|add\w*|li|mr|subf\w*|and|or) ')


def batch_normalization(body):
    ops = list(re.finditer(r'\t// ([^\n]+)\n(.*?)(?=\t// |\nloc_|\n\}|$)', body, re.S))
    refs = [set(re.findall(r'ctx\.(v\d+)\b', m[2])) for m in ops]
    writes = []
    eligible = []
    for i, op in enumerate(ops):
        # Reject ambiguous vector writes rather than inferring from a mnemonic.
        destination = op[1].split(' ', 1)[-1].split(',')[0]
        writes.append(destination if destination in refs[i] else None)
        match = RSQRT.fullmatch(op[1])
        if match:
            dst, src = match.groups()
            exact = f'\tsimde_mm_store_ps(ctx.{dst}.f32, simde_mm_div_ps(simde_mm_set1_ps(1), simde_mm_sqrt_ps(simde_mm_load_ps(ctx.{src}.f32))));\n'
            if op[2].rstrip('\n') != exact.rstrip('\n'):
                raise ValueError('Unrecognized reciprocal-square-root emission')
            eligible.append((i, dst, src))
    groups = []
    used = set()
    candidates = [g for size in (4,3,2) for g in sorted(
        itertools.combinations(eligible, size), key=lambda g: g[-1][0]-g[0][0])]
    for group in candidates:
        if any(i in used for i, _, _ in group):
            continue
        destinations = [d for _, d, _ in group]
        if len(set(destinations)) != len(group) or any(
                d == s for k, (_, d, _) in enumerate(group)
                for j, (_, _, s) in enumerate(group) if k != j):
            continue
        for point in range(group[0][0], group[-1][0]+1):
            valid = True
            for i, dst, src in group:
                definition = next((j for j in range(i-1, -1, -1) if writes[j] == src), None)
                if definition is None or definition >= point:
                    valid = False
                    break
                reaching = body[ops[definition].start():ops[i].start()]
                if ('\nloc_' in reaching or 'goto ' in reaching or
                    re.search(r'\t\w+\(ctx, base\);', reaching) or 'fpscr' in reaching):
                    valid = False
                    break
                dot = ops[definition]
                if not re.fullmatch(r'vmsum[34]fp128 '+src+r',v\d+,v\d+', dot[1]) or ', 0xEF));' not in dot[2] and ', 0xFF));' not in dot[2]:
                    valid = False
                    break
                # Labels, memory accesses, calls and FP-control changes cannot
                # cross a moved operation, even if vector register names differ.
                for j in range(min(i, point), max(i, point)+1):
                    if j == i:
                        continue
                    if (dst in refs[j] or writes[j] == src or
                        not PURE.match(ops[j][1]) or 'fpscr' in ops[j][2] or
                        'REX_' in ops[j][2] or 'goto ' in ops[j][2] or
                        '\nloc_' in body[ops[min(i,point)].start():ops[max(i,point)].end()]):
                        valid = False
                        break
                if not valid:
                    break
            if valid:
                start=min(point,group[0][0]);end=max(point,group[-1][0])
                destinations={d for _,d,_ in group}
                operands={r for _,d,s in group for r in (d,s)}
                # Independently legal moves must also remain legal together.
                # Overlapping schedules cannot exchange reused vector values.
                for other_point,other in groups:
                    other_start=min(other_point,other[0][0]);other_end=max(other_point,other[-1][0])
                    if start<=other_end and other_start<=end:
                        other_destinations={d for _,d,_ in other}
                        other_operands={r for _,d,s in other for r in (d,s)}
                        if destinations & other_operands or other_destinations & operands:
                            valid=False
                            break
                if not valid:
                    continue
                groups.append((point, group))
                used.update(i for i, _, _ in group)
                break
    changes = {}
    calls = {}
    for point, group in groups:
        args = ', '.join('ctx.'+d for _, d, _ in group) + ', ' + ', '.join('ctx.'+s for _, _, s in group)
        for i, _, _ in group:
            changes[i] = ops[i][0].replace(ops[i][2], '\tif (!native_batch) {\n'+ops[i][2].rstrip('\n')+'\n\t}\n')
        calls[point] = calls.get(point, '') + f'\tif (native_batch) Ch2k8ReciprocalSqrt{len(group)}('+args+');\n'
    for point, call in calls.items():
        changes[point] = call + changes.get(point, ops[point][0])
    for i in sorted(changes, reverse=True):
        body = body[:ops[i].start()] + changes[i] + body[ops[i].end():]
    return body, len(groups)
