"""Exercise the actual pinned video export and adapter preparation."""
import subprocess
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from prepare_display_sdk import prepare_display, patch_video, patch_adapter

SOURCE = ROOT/'work/third_party/rexglue-vulkan'
VIDEO = 'src/kernel/xboxkrnl/xboxkrnl_video.cpp'
ADAPTER = 'src/ui/d3d12/d3d12_provider.cpp'


def original(relative):
    if not (SOURCE/'.git').exists():
        pytest.skip('Pinned source SDK required')
    return subprocess.check_output(['git','-C',str(SOURCE),'show','HEAD:'+relative],text=True)


def test_preparation_is_idempotent_and_rejects_unknown_changes_before_writing(tmp_path):
    originals = {relative: original(relative) for relative in (VIDEO, ADAPTER)}
    for relative, text in originals.items():
        path = tmp_path/relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    subprocess.run(['git','init',str(tmp_path)],check=True,capture_output=True)
    subprocess.run(['git','-C',str(tmp_path),'add','.'],check=True,capture_output=True)
    subprocess.run(['git','-C',str(tmp_path),'-c','user.name=test','-c','user.email=test@example.com',
                    'commit','-m','fixture'],check=True,capture_output=True)
    prepare_display(tmp_path)
    expected = {r:(tmp_path/r).read_bytes() for r in originals}
    prepare_display(tmp_path)
    assert expected == {r:(tmp_path/r).read_bytes() for r in originals}
    (tmp_path/VIDEO).write_text(originals[VIDEO])
    (tmp_path/ADAPTER).write_text(originals[ADAPTER]+'\n// unknown edit\n')
    with pytest.raises(ValueError, match='Unreviewed'):
        prepare_display(tmp_path)
    assert (tmp_path/VIDEO).read_text() == originals[VIDEO]


def test_guest_refresh_export_uses_independent_default_60_hz():
    text = patch_video(original(VIDEO))
    assert 'ch2k8_guest_refresh_rate, 60.0' in text
    assert 'std::clamp(REXCVAR_GET(ch2k8_guest_refresh_rate), 24.0, 240.0)' in text
    assert 'std::clamp(REXCVAR_GET(video_mode_refresh_rate)' not in text


def test_only_automatic_gpu_selection_uses_high_performance_order():
    text = patch_adapter(original(ADAPTER))
    assert 'if (REXCVAR_GET(d3d12_adapter) == -1)' in text
    assert 'DXGI_GPU_PREFERENCE_HIGH_PERFORMANCE' in text
    assert ': dxgi_factory->EnumAdapters1(index, result)' in text
    assert 'adapter_index == REXCVAR_GET(d3d12_adapter)' in text
    assert 'adapter_desc.Flags & DXGI_ADAPTER_FLAG_SOFTWARE' in text


def test_real_guest_refresh_getter_ignores_monitor_rate(tmp_path):
    compiler = shutil.which('clang++')
    if not compiler:
        pytest.skip('Clang required')
    text = patch_video(original(VIDEO))
    start = text.index('float GetConfiguredVideoModeRefreshRate() {')
    getter = text[start:text.index('\n}', start)+2]
    source = tmp_path/'refresh.cpp'
    source.write_text('''#include <algorithm>
#include <cassert>
double ch2k8_guest_refresh_rate=60, video_mode_refresh_rate=120;
#define REXCVAR_GET(name) name
'''+getter+'''
int main() {
  for(double host: {60.,120.,144.,240.}) {
    video_mode_refresh_rate=host;
    assert(GetConfiguredVideoModeRefreshRate()==60.f);
  }
  ch2k8_guest_refresh_rate=120;
  assert(GetConfiguredVideoModeRefreshRate()==120.f);
  ch2k8_guest_refresh_rate=0;
  assert(GetConfiguredVideoModeRefreshRate()==24.f);
  ch2k8_guest_refresh_rate=1000;
  assert(GetConfiguredVideoModeRefreshRate()==240.f);
}
''')
    executable = tmp_path/'refresh.exe'
    result = subprocess.run([compiler,'-std=c++17',str(source),'-o',str(executable)],capture_output=True,text=True)
    assert result.returncode == 0, result.stderr
    subprocess.run([str(executable)],check=True)
