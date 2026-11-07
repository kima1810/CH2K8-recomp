import sys
from pathlib import Path
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from summarize_gpu_wait import summarize


def test_gpu_wait_summary_separates_threads_and_reports_coarse_cpu(tmp_path):
    path=tmp_path/'runtime.log'
    path.write_text('[2026-11-03 12:00:00.000] [info] start\n'
        '[2026-11-03 12:02:00.100] [info] [t10] CH2K8_GPU_WAIT waits=100 notifications=10 timeouts=90 wall_ms=900 address=FFCA3000 window_ms=1000 cpu_ms=31.25\n'
        '[2026-11-03 12:02:01.100] [info] [t11] CH2K8_GPU_WAIT waits=10 notifications=5 timeouts=5 wall_ms=8 address=FFCA3004 window_ms=1000 cpu_ms=-1\n')
    rows=summarize(path)['threads']
    assert rows['10']['wait_window_fraction']==0.9
    assert rows['10']['thread_cpu_window_fraction']==0.03125
    assert rows['10']['average_wait_ms']==9
    assert rows['11']['thread_cpu_window_fraction'] is None
    assert rows['11']['addresses']==['FFCA3004']


def test_gpu_wait_summary_rejects_inconsistent_or_nonfinite_bins(tmp_path):
    path=tmp_path/'runtime.log'
    for values in ['waits=2 notifications=1 timeouts=2 wall_ms=1 window_ms=1000 cpu_ms=0',
                   'waits=2 notifications=1 timeouts=1 wall_ms=nan window_ms=1000 cpu_ms=0']:
        path.write_text('[2026-11-03 12:00:00.000] [info] start\n'
            '[2026-11-03 12:02:01.000] [info] [t10] CH2K8_GPU_WAIT '+values+' address=FFCA3000\n')
        with pytest.raises(ValueError):summarize(path)
