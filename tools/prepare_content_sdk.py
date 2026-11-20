"""Prevent repeated visits to the same aggregate-content enumeration root."""
from pathlib import Path


def prepare_content(source):
    path=source/'src/kernel/xam/xam_content_aggregate.cpp'
    text=path.read_text(encoding='utf-8')
    marker='// CH2K8 unique content enumeration roots v1'
    if marker not in text:
        changes={
            '#include <rex/system/xtypes.h>':'#include <rex/system/xtypes.h>\n#include <rex/system/xam/ch2k8_content_roots.h>\n'+marker,
            '    for (auto& title_id : title_ids) {':'    ::ch2k8::ContentRoots enumeration_roots;\n    for (auto& title_id : title_ids) {\n      if (!enumeration_roots.First(xuid, title_id, REX_KERNEL_STATE()->title_id())) continue;',
            '      if (userxuid != 0) {':'      if (userxuid != 0 &&\n          enumeration_roots.First(0, title_id, REX_KERNEL_STATE()->title_id())) {'}
        for before in changes:
            if text.count(before)!=1:raise ValueError('Unrecognized aggregate-content patch site: '+before)
        for before,after in changes.items():text=text.replace(before,after,1)
        path.write_text(text,encoding='utf-8',newline='\n')
    path=source/'src/kernel/xam/xam_content.cpp'
    text=path.read_text(encoding='utf-8')
    marker='// CH2K8 XUSER_INDEX_NONE lists common content v1'
    if marker not in text:
        # The title enumerates each device for its profile (user 0) and for XUSER_INDEX_NONE (0xFE), then merges
        # both lists. 0xFE means content tied to no user, so it lists common (xuid 0) content only; otherwise
        # every save appears twice on the Load screen.
        enumerator='\n\n  auto e = make_object<XStaticEnumerator<XCONTENT_DATA>>(REX_KERNEL_STATE(), items_per_enumerate);'
        before='  uint64_t xuid = REX_KERNEL_STATE()->user_profile()->xuid();'+enumerator
        if text.count(before)!=1:raise ValueError('Unrecognized content enumerator patch site: '+before)
        text=text.replace(before,'  '+marker+'\n  uint64_t xuid = user_index == 0xFE ? 0 : REX_KERNEL_STATE()->user_profile()->xuid();'+enumerator,1)
        path.write_text(text,encoding='utf-8',newline='\n')
    destination=source/'include/rex/system/xam/ch2k8_content_roots.h'
    destination.write_bytes((Path(__file__).resolve().parents[1]/'port/src/content_roots.h').read_bytes())
