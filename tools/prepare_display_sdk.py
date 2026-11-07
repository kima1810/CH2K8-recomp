"""Separate guest timing from monitor mode and prefer the high-performance GPU."""
from pathlib import Path
import subprocess
from prepare_native_gpu_sdk import replace_once


def patch_video(text):
    text = replace_once(text, 'namespace {\n', '''REXCVAR_DEFINE_DOUBLE(ch2k8_guest_refresh_rate, 60.0, "Display/CH2K8",
                      "Guest video and VBlank rate, independent of the monitor mode")
    .lifecycle(rex::cvar::Lifecycle::kInitOnly);

namespace {
''')
    return replace_once(text,
        'std::clamp(REXCVAR_GET(video_mode_refresh_rate), 24.0, 240.0)',
        'std::clamp(REXCVAR_GET(ch2k8_guest_refresh_rate), 24.0, 240.0)')


def patch_adapter(text):
    text = replace_once(text, '#include <cstdlib>', '#include <cstdlib>\n#include <dxgi1_6.h>')
    text = replace_once(text, '  // Choose the adapter.\n', '''  // CH2K8: automatic selection follows Windows high-performance preference.
  // Explicit adapter indices retain legacy DXGI enumeration order.
  Microsoft::WRL::ComPtr<IDXGIFactory6> preferred_factory;
  if (REXCVAR_GET(d3d12_adapter) == -1) {
    dxgi_factory->QueryInterface(IID_PPV_ARGS(&preferred_factory));
  }
  REXLOG_INFO("CH2K8 GPU selection: {}",
              preferred_factory ? "high-performance preference" : "legacy / explicit index");
  const auto enumerate_adapter = [&](uint32_t index, IDXGIAdapter1** result) {
    return preferred_factory
        ? preferred_factory->EnumAdapterByGpuPreference(index, DXGI_GPU_PREFERENCE_HIGH_PERFORMANCE,
                                                       IID_PPV_ARGS(result))
        : dxgi_factory->EnumAdapters1(index, result);
  };
''')
    return replace_once(text, 'dxgi_factory->EnumAdapters1(adapter_index, &adapter)',
                        'enumerate_adapter(adapter_index, &adapter)')


def prepare_display(source: Path):
    changes = {}
    for relative, patch in (
        ('src/kernel/xboxkrnl/xboxkrnl_video.cpp', patch_video),
        ('src/ui/d3d12/d3d12_provider.cpp', patch_adapter),
    ):
        original = subprocess.check_output(['git', '-C', str(source), 'show', 'HEAD:'+relative], text=True)
        expected = patch(original)
        path = source / relative
        if path.read_text(encoding='utf-8') not in (original, expected):
            raise ValueError('Unreviewed display SDK source: '+relative)
        changes[path] = expected
    for path, expected in changes.items():
        if path.read_text(encoding='utf-8') != expected:
            path.write_text(expected, encoding='utf-8', newline='\n')
