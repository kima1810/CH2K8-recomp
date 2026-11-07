"""Preserve the output reference while the native presentation wait is unlocked."""
from pathlib import Path
import subprocess
from prepare_native_gpu_sdk import replace_once
ROOT=Path(__file__).resolve().parents[1]


def patch_presenter(text):
    if '// CH2K8 retained vblank output v1' in text or '// CH2K8 adaptive native presentation pacing v1' in text:return text
    return replace_once(text,'      wait_succeeded = SUCCEEDED(dxgi_ui_tick_output_->WaitForVBlank());',
        '      // CH2K8 retained vblank output v1: the shared member may change after unlock.\n'
        '      wait_succeeded = SUCCEEDED(dxgi_output->WaitForVBlank());')


def scope_function(text,signature,stage):
    start=text.index(signature)
    at=text.index('{\n',start)+2
    return text[:at]+f'  ch2k8::PresentScope native_present_scope(ch2k8::PresentStage::{stage});\n'+text[at:]


def patch_presenter_stats(text):
    text=patch_presenter(text)
    if '// CH2K8 native presentation timing v1' in text:return text
    text=replace_once(text,'#include <rex/ui/presenter.h>',
        '#include <rex/ui/presenter.h>\n#include <rex/ui/native_present_stats.h>\n// CH2K8 native presentation timing v1')
    text=replace_once(text,'REXCVAR_DEFINE_BOOL(host_present_from_non_ui_thread,',
        'REXCVAR_DEFINE_BOOL(ch2k8_present_stats, false, "UI/CH2K8",\n'
        '                    "Opt-in native presentation wall/CPU timing")\n'
        '    .lifecycle(rex::cvar::Lifecycle::kInitOnly);\n\n'
        'REXCVAR_DEFINE_BOOL(host_present_from_non_ui_thread,')
    text=scope_function(text,'void Presenter::WaitForUITickFromUIThread()', 'UITick')
    text=scope_function(text,'bool Presenter::RefreshGuestOutput(', 'Publish')
    text=replace_once(text,'      Microsoft::WRL::ComPtr<IDXGIOutput> dxgi_output = dxgi_ui_tick_output_;',
        '      ch2k8::PresentScope native_vblank_scope(ch2k8::PresentStage::VBlank);\n'
        '      Microsoft::WRL::ComPtr<IDXGIOutput> dxgi_output = dxgi_ui_tick_output_;')
    return text


def patch_d3d12_presenter_stats(text):
    if '// CH2K8 D3D12 presentation timing v1' in text:return text
    # Only instrument the native presenter; no game frame or GPU commands change.
    text=replace_once(text,'#include <rex/ui/d3d12/d3d12_presenter.h>',
        '#include <rex/ui/d3d12/d3d12_presenter.h>\n#include <rex/ui/native_present_stats.h>\n// CH2K8 D3D12 presentation timing v1')
    text=scope_function(text,'Presenter::PaintResult D3D12Presenter::PaintAndPresentImpl(', 'Paint')
    text=scope_function(text,'bool D3D12Presenter::RefreshGuestOutputImpl(', 'Refresh')
    start=text.index('  HRESULT present_result = paint_context_.swap_chain->Present(')
    end=text.index(';\n',start)+2
    statement=text[start:end].replace('HRESULT present_result =','present_result =',1)
    text=text[:start]+'  HRESULT present_result;\n  {\n    ch2k8::PresentScope native_present(ch2k8::PresentStage::Present);\n'+statement+'  }\n'+text[end:]
    site='  provider_.GetDirectQueue()->ExecuteCommandLists(1, &execute_command_list);'
    text=replace_once(text,site,'  {\n    ch2k8::PresentScope native_queue(ch2k8::PresentStage::Queue);\n'+site+'\n  }')
    # The whole acquisition block includes time waiting on the mailbox lock.
    site='    uint32_t guest_output_mailbox_index;'
    # Two blocks use this spelling: capture and paint. Instrument both, since
    # diagnostic readback itself must not be mistaken for normal presentation.
    text=text.replace(site,'    ch2k8::PresentScope native_mailbox(ch2k8::PresentStage::Mailbox);\n'+site)
    site='paint_context_.paint_submission_tracker.AwaitSubmissionCompletion('
    positions=[];at=0
    while (at:=text.find(site,at))!=-1:
        end=text.index(';',at)+1;positions.append((at,end));at=end
    for at,end in reversed(positions):
        text=text[:at]+'{ ch2k8::PresentScope native_fence(ch2k8::PresentStage::Fence);\n'+text[at:end]+' }'+text[end:]
    return text


def patch_presenter_pacing(text):
    text=patch_presenter_stats(text)
    if '// CH2K8 adaptive native presentation pacing v1' in text:return text
    text=replace_once(text,'#include <rex/ui/native_present_stats.h>',
        '#include <rex/ui/native_present_stats.h>\n#include <rex/ui/native_vblank_pacer.h>')
    text=replace_once(text,'REXCVAR_DEFINE_BOOL(ch2k8_present_stats,',
        'REXCVAR_DEFINE_BOOL(ch2k8_native_present_pacing, true, "UI/CH2K8",\n'
        '                    "Pace native UI redraws if DXGI VBlank returns immediately")\n'
        '    .lifecycle(rex::cvar::Lifecycle::kInitOnly);\n\n'
        'REXCVAR_DEFINE_BOOL(ch2k8_present_stats,')
    start=text.index('void Presenter::DXGIUITickThread() {')
    end=text.index('\n}\n',start)+3
    return text[:start]+'// CH2K8 adaptive native presentation pacing v1\n#include "ch2k8_vblank_thread.inl"\n'+text[end:]


def prepare_native_presenter(source: Path):
    changes={}
    for relative,patch in [('src/ui/presenter.cpp',patch_presenter_pacing),
        ('src/ui/d3d12/d3d12_presenter.cpp',patch_d3d12_presenter_stats)]:
        original=subprocess.check_output(['git','-C',str(source),'show','HEAD:'+relative],text=True)
        expected=patch(original);path=source/relative
        legacy=patch_presenter(original) if relative=='src/ui/presenter.cpp' else original
        timing=patch_presenter_stats(original) if relative=='src/ui/presenter.cpp' else original
        if path.read_text(encoding='utf-8') not in (original,legacy,timing,expected):
            raise ValueError('Unreviewed native presenter source')
        changes[path]=expected
    for path,expected in changes.items():
        if path.read_text(encoding='utf-8')!=expected:path.write_text(expected,encoding='utf-8',newline='\n')
    destination=source/'include/rex/ui/native_present_stats.h'
    destination.parent.mkdir(parents=True,exist_ok=True)
    data=(ROOT/'port/sdk_patches/native_present_stats.h').read_bytes()
    if not destination.exists() or destination.read_bytes()!=data:destination.write_bytes(data)
    for name,target in [('native_vblank_pacer.h','include/rex/ui/native_vblank_pacer.h'),
                        ('native_vblank_thread.inl','src/ui/ch2k8_vblank_thread.inl')]:
        destination=source/target;data=(ROOT/'port/sdk_patches'/name).read_bytes()
        if not destination.exists() or destination.read_bytes()!=data:destination.write_bytes(data)
