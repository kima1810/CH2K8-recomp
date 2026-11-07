import csv
import shutil
import subprocess
from pathlib import Path

import pytest
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from summarize_guest_frames import summarize


def test_submission_summary_excludes_first_zero_interval(tmp_path):
    path = tmp_path/'frames.csv'
    path.write_text('elapsed_ms,submit_interval_ms,swap_wall_ms,swap_thread_cpu_ms\n'
                    '10,0,0.002,0\n30,20,0.001,0\n50,20,0.003,0\n')
    result = summarize(path)
    assert result['submissions'] == 3
    assert result['median_submission_hz'] == 50
    assert summarize(path, .03, .05)['submissions'] == 1


def test_optional_frame_log_has_valid_intervals_and_safe_shutdown(tmp_path):
    compiler = shutil.which('clang++')
    if not compiler:
        pytest.skip('Requires clang++')
    root = Path(__file__).resolve().parents[1]
    source = tmp_path / 'probe.cpp'
    source.write_text('''
#include <chrono>
#include <thread>
#include <cassert>
bool Ch2k8OpenFrameLog(const char*);
void Ch2k8CloseFrameLog();
void Ch2k8BeforeSwap();
void Ch2k8AfterSwap();
int main(int argc,char**argv) {
 Ch2k8BeforeSwap(); Ch2k8AfterSwap();
 assert(Ch2k8OpenFrameLog(argv[1]));
 for(int i=0;i<2;++i) {
  Ch2k8BeforeSwap();
  std::this_thread::sleep_for(std::chrono::milliseconds(10));
  Ch2k8AfterSwap();
 }
 Ch2k8CloseFrameLog();
 Ch2k8BeforeSwap(); Ch2k8AfterSwap(); Ch2k8CloseFrameLog();
}
''')
    executable = tmp_path / 'probe.exe'
    output = tmp_path / 'frames with spaces.csv'
    compilation = subprocess.run([compiler, '-std=c++23', '-O2', str(source),
        str(root/'port/src/frame_timing.cpp'), '-o', str(executable)], capture_output=True, text=True)
    assert compilation.returncode == 0, compilation.stderr
    execution = subprocess.run([str(executable), str(output)], capture_output=True, text=True)
    assert execution.returncode == 0, execution.stderr
    rows = list(csv.DictReader(output.open()))
    assert len(rows) == 2
    assert float(rows[0]['submit_interval_ms']) == 0
    assert float(rows[1]['submit_interval_ms']) >= 5
    assert all(float(row['swap_wall_ms']) >= 5 for row in rows)


def test_generated_swap_probes_bracket_original_import_call():
    root = Path(__file__).resolve().parents[1]
    generated = root/'port/generated/default'
    if not generated.exists():
        pytest.skip('Requires locally generated game code')
    for path in generated.glob('*_recomp.*.cpp'):
        text = path.read_text()
        if '__imp__VdSwap(ctx, base);' in text:
            before = text.index('\tCh2k8BeforeSwap();')
            swap = text.index('__imp__VdSwap(ctx, base);', before)
            after = text.index('Ch2k8AfterSwap();', swap)
            assert before < swap < after
            assert after - before < 500
            return
    pytest.fail('No generated VdSwap import call found')
