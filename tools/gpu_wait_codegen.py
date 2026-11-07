"""Add a bounded native wait to the audited GPU-counter retry backedge."""
import hashlib
from pathlib import Path

MARKER='// CH2K8 native GPU progress wait v1\n#include "native_gpu_wait.h"\n'
SIGNATURE='DEFINE_REX_FUNC(sub_84DDA4D0) {'
DIGEST='65f2f6859af1e02ce7cf0337a4d7100000f4f3514d4980a96fcc99119dff33a2'
LOCALS='\tCh2k8GpuWait native_gpu_wait;\n\tuint32_t native_wait_address=0;\n'
CAPTURE='\tnative_wait_address=ctx.r10.u32;\n'
OLD='\tif (ctx.cr6.lt) goto loc_84DDA558;'
NEW='''\tif (ctx.cr6.lt) {
\t\tif (native_gpu_wait.enabled()) native_gpu_wait.Poll(base,native_wait_address,
\t\t    ctx.r10.u32,ctx.r31.u32+10908,ctx.r11.u32+ctx.r10.u32);
\t\tgoto loc_84DDA558;
\t}'''


def prepare_source(text):
    if SIGNATURE not in text:return text
    original=text
    patched=text.startswith(MARKER)
    if patched:text=text[len(MARKER):]
    start=text.index(SIGNATURE);end=text.index('\n}\n',start)+3
    body=text[start:end]
    if patched:
        if body.count(LOCALS)!=1 or body.count(CAPTURE)!=1 or body.count(NEW)!=1:
            raise ValueError('Unknown native GPU wait emission')
        body=body.replace(LOCALS,'',1).replace(CAPTURE,'',1).replace(NEW,OLD,1)
    if hashlib.sha256(body.encode()).hexdigest()!=DIGEST:
        raise ValueError('GPU-counter wait body changed; re-audit required')
    body=body.replace(SIGNATURE+'\n',SIGNATURE+'\n'+LOCALS,1)
    site='''\t// lwz r10,0(r10)
\tctx.r10.u64 = REX_LOAD_U32(ctx.r10.u32 + 0);'''
    # The earlier preflight reads retain their exact positions. Capture only
    # the word used by the loop's own completion comparison.
    loop=body.index('loc_84DDA568:')
    after=body[loop:]
    if after.count(site)!=1:raise ValueError('Unknown GPU-counter loop load')
    after=after.replace(site,site.split('\n')[0]+'\n'+CAPTURE+site.split('\n')[1],1)
    body=body[:loop]+after
    if body.count(OLD)!=1:raise ValueError('Unknown GPU-counter retry branch')
    body=body.replace(OLD,NEW,1)
    result=MARKER+text[:start]+body+text[end:]
    return result if result!=original else original


def prepare_directory(generated):
    changed=0
    for path in sorted(Path(generated).glob('*_recomp.*.cpp')):
        text=path.read_text()
        if SIGNATURE not in text:continue
        result=prepare_source(text)
        if result!=text:path.write_text(result,newline='\n');changed+=1
    return changed
