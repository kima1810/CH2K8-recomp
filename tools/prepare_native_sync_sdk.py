"""Checked opt-in synchronization attribution; leaves all waits intact."""
from pathlib import Path
import subprocess
from prepare_native_gpu_sdk import replace_once, patch_common, patch_backend
ROOT=Path(__file__).resolve().parents[1]

def patch_sync_v1(text, kind):
    if '// CH2K8 sync attribution v1' in text: return text
    text=replace_once(text,'#include <rex/graphics/flags.h>',
        '#include <rex/graphics/flags.h>\n#include <rex/graphics/native_sync_stats.h>\n// CH2K8 sync attribution v1')
    if kind=='common':
        site='    if (write_ptr_index == 0xBAADF00D || read_ptr_index_ == write_ptr_index) {\n'
        text=replace_once(text,site,site+'      ch2k8::SyncScope native_sync(ch2k8::SyncKind::RingIdle);\n')
        site='bool CommandProcessor::ExecutePacketType3_WAIT_REG_MEM(memory::RingBuffer* reader, uint32_t packet,\n                                                       uint32_t count) {\n'
        text=replace_once(text,site,site+'  ch2k8::SyncScope native_sync(ch2k8::SyncKind::RegisterWait);\n')
    else:
        site='void D3D12CommandProcessor::CheckSubmissionFence(uint64_t await_submission) {\n'
        text=replace_once(text,site,site+'  ch2k8::SyncScope native_sync(ch2k8::SyncKind::SubmissionFence);\n')
    return text

def patch_sync_attribution(text, kind):
    text=patch_sync_v1(text,kind)
    if kind!='common' or '// CH2K8 wait detail v1' in text:return text
    start=text.index('bool CommandProcessor::ExecutePacketType3_WAIT_REG_MEM(')
    end=text.index('\n}\n',start)
    part=text[start:end]
    site='  bool is_memory = (wait_info & 0x10) != 0;\n'
    part=replace_once(part,site,site+'  // CH2K8 wait detail v1\n  ch2k8::WaitDetail native_wait(wait_info,poll_reg_addr,ref,mask,wait);\n')
    part=replace_once(part,'    if (!matched) {','    if (!matched) {\n      native_wait.Poll(value);')
    return text[:start]+part+text[end:]


def patch_sync(text,kind):
    text=patch_sync_attribution(text,kind)
    if kind!='common' or '// CH2K8 GPU progress notification v1' in text:return text
    text=replace_once(text,'#include <rex/graphics/native_sync_stats.h>',
        '#include <rex/graphics/native_sync_stats.h>\n#define CH2K8_GPU_PROGRESS_EXPORTS\n#include <rex/graphics/native_gpu_progress.h>\n// CH2K8 GPU progress notification v1')
    site='      memory::store_and_swap<uint32_t>(memory_->TranslatePhysical(read_ptr_writeback_ptr_),\n                                       read_ptr_index_);\n'
    text=replace_once(text,site,site+'      ch2k8::NativeGpuProgress().Notify();\n')
    site='  memory::store(memory_->TranslatePhysical(address), data_value);\n'
    return replace_once(text,site,site+'  ch2k8::NativeGpuProgress().Notify();\n')


def prepare_sync(source):
    changes={}
    for relative,kind in [('src/graphics/command_processor.cpp','common'),('src/graphics/d3d12/command_processor.cpp','d3d12')]:
        original=subprocess.check_output(['git','-C',str(source),'show','HEAD:'+relative],text=True)
        previous=patch_common(original) if kind=='common' else patch_backend(original,kind)
        expected=patch_sync(previous,kind); path=source/relative
        if path.read_text(encoding='utf-8') not in (previous,patch_sync_v1(previous,kind),patch_sync_attribution(previous,kind),expected):
            raise ValueError('Unreviewed synchronization source: '+relative)
        changes[path]=expected
    for path,text in changes.items():
        if path.read_text(encoding='utf-8')!=text:path.write_text(text,encoding='utf-8',newline='\n')
    path=source/'include/rex/graphics/native_sync_stats.h'; data=(ROOT/'port/sdk_patches/native_sync_stats.h').read_bytes()
    path.parent.mkdir(parents=True,exist_ok=True)
    if not path.exists() or path.read_bytes()!=data:path.write_bytes(data)

    path=source/'include/rex/graphics/native_gpu_progress.h';data=(ROOT/'port/sdk_patches/native_gpu_progress.h').read_bytes()
    if not path.exists() or path.read_bytes()!=data:path.write_bytes(data)
