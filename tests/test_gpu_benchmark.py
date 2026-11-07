import json
import shutil
import subprocess
import sys
import struct
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from summarize_gpu_run import summarize_run, inspect_native_readback


@pytest.mark.parametrize('mode,flag',[('baseline','--no-ch2k8_native_gpu_wait'),('optimized','--ch2k8_native_gpu_wait')])
def test_gpu_wait_and_process_affinity_controls_are_explicit(tmp_path,mode,flag):
    shell=shutil.which('powershell.exe')
    if not shell:pytest.skip('Requires Windows PowerShell')
    data=tmp_path/'disc';data.mkdir();(data/'default.xex').touch()
    executable=tmp_path/'unused.exe';executable.touch()
    result=subprocess.run([shell,'-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'tools/benchmark_gpu_path.ps1'),
        '-ValidateOnly','-GameData',str(data),'-Executable',str(executable),'-NativeGpuWait',mode,'-GpuWaitStats','-CpuAffinityMask','5'],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    config=json.loads(result.stdout)
    assert config['cpu_affinity_mask']=='0x5'
    assert flag in config['arguments'] and '--ch2k8_gpu_wait_stats' in config['arguments']
    assert not Path(config['run_root']).exists()


@pytest.mark.parametrize('pacing,flag',[('baseline','--no-ch2k8_native_present_pacing'),('optimized','--ch2k8_native_present_pacing')])
def test_visible_presentation_diagnostic_controls(tmp_path,pacing,flag):
    shell=shutil.which('powershell.exe')
    if not shell:pytest.skip('Requires Windows PowerShell')
    data=tmp_path/'disc';data.mkdir();(data/'default.xex').touch()
    executable=tmp_path/'unused.exe';executable.touch()
    result=subprocess.run([shell,'-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'tools/benchmark_gpu_path.ps1'),
        '-ValidateOnly','-GameData',str(data),'-Executable',str(executable),'-Visible','-PresentStats','-PresentPacing',pacing],
        capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    config=json.loads(result.stdout)
    assert config['visible_window'] is True
    assert flag in config['arguments'] and '--ch2k8_present_stats' in config['arguments']
    assert not Path(config['run_root']).exists()


@pytest.mark.parametrize('profile,backend,target,batching', [
    ('d3d12-rov', 'd3d12', '--render_target_path_d3d12=rov', False),
    ('d3d12-rov-batched', 'd3d12', '--render_target_path_d3d12=rov', True),
    ('d3d12-rtv', 'd3d12', '--render_target_path_d3d12=rtv', False),
    ('d3d12-rtv-extent', 'd3d12', '--render_target_path_d3d12=rtv', False),
    ('vulkan-fbo', 'vulkan', '--render_target_path_vulkan=fbo', False),
    ('vulkan-fsi', 'vulkan', '--render_target_path_vulkan=fsi', False),
    ('vulkan-fbo-batched', 'vulkan', '--render_target_path_vulkan=fbo', True),
    ('vulkan-fsi-batched', 'vulkan', '--render_target_path_vulkan=fsi', True),
])
def test_gpu_profiles_launch_the_requested_path_without_changing_coherence(tmp_path, profile, backend, target, batching):
    shell = shutil.which('powershell.exe')
    if not shell:
        pytest.skip('Requires Windows PowerShell')
    data = tmp_path/'disc with spaces'
    data.mkdir()
    (data/'default.xex').write_bytes(b'')
    executable = tmp_path/'unused executable.exe'
    executable.write_bytes(b'')
    command = [shell, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
               str(ROOT/'tools/benchmark_gpu_path.ps1'), '-ValidateOnly', '-Profile', profile,
               '-GameData', str(data), '-Executable', str(executable)]
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    config = json.loads(result.stdout)
    args = config['arguments']
    assert f'--ch2k8_renderer={backend}' in args and target in args
    assert f'--game_data_root={data}' in args
    assert (f'--no-{backend}_submit_on_primary_buffer_end' in args) == batching
    assert ('--execute_unclipped_draw_vs_on_cpu' in args) == profile.endswith('-extent')
    assert not any('readback' in arg or 'occlusion' in arg for arg in args)
    assert '--ch2k8_output_capture_count=2' in args
    assert config['capture_seconds'] == 210 and not config['matched_scene']
    assert config['visible_window'] is False
    assert not Path(config['run_root']).exists()
    (data/'default.xex').unlink()
    failure = subprocess.run(command, capture_output=True, text=True)
    assert failure.returncode != 0 and 'default.xex' in failure.stderr


@pytest.mark.parametrize('effective,verified', [('0x5', True), ('0xffff', False), ('', False)])
def test_gpu_summary_verifies_effective_affinity(tmp_path, effective, verified):
    (tmp_path/'run.json').write_text(json.dumps({'cpu_affinity_mask':'0x5'}))
    (tmp_path/'process.csv').write_text(
        'elapsed_s,cpu_time_s,working_set_bytes,threads,cpu_affinity_mask\n'
        f'120,200,1024,10,{effective}\n130,210,1024,10,{effective}\n')
    assert summarize_run(tmp_path)['cpu_affinity_verified'] is verified


def test_gpu_summary_keeps_unsupported_sensors_and_timing_limits(tmp_path):
    (tmp_path/'run.json').write_text(json.dumps({'profile': 'vulkan-fbo', 'executable_sha256': 'abc'}))
    (tmp_path/'guest-frames.csv').write_text(
        'elapsed_ms,submit_interval_ms,swap_wall_ms,swap_thread_cpu_ms\n'
        '1000,16,1,0\n120000,50,0.002,0\n121000,60,0.003,0\n')
    (tmp_path/'process.csv').write_text(
        'elapsed_s,cpu_time_s,working_set_bytes,threads\n'
        '120,200,1024,10\n130,230,2048,11\n')
    (tmp_path/'amd.csv').write_text('second,gfx_clock_raw,gfx_activity_raw,throttler_raw\n'
                                 '10,200,20,0\n120,2600,80,NA\n130,2700,90,NA\n')
    (tmp_path/'runtime.log').write_text('Creating graphics pipeline state\n'
                                      'Skipping Vulkan frame presentation\n')
    result = summarize_run(tmp_path)
    assert result['guest_submissions']['submissions'] == 2
    assert result['mean_process_cpu_cores'] == 3
    assert result['peak_sampled_working_set_bytes'] == 2048
    assert result['amd_raw_sensor_medians']['gfx_clock_raw'] == 2650
    assert result['amd_raw_sensor_medians']['throttler_raw'] is None
    assert result['pipeline_creation_log_entries'] == 1
    assert result['placeholder_presentation_skip_entries'] == 1
    assert not result['matched_scene']
    assert 'not unique displayed FPS' in result['limits']


def test_gpu_constant_bins_use_log_timestamps_and_weight_packet_work(tmp_path):
    (tmp_path/'run.json').write_text(json.dumps({'started':'2026-11-01T10:00:00-05:00'}))
    (tmp_path/'runtime.log').write_text(
        '[2026-11-01 10:00:01.000] CH2K8_GPU_CONSTANTS native=true single=999 ranges=0 words=999 skipped=999 skipped_words=999 float_uploads=999 system_uploads=999 bool_uploads=0\n'
        '[2026-11-01 10:02:10.000] CH2K8_GPU_CONSTANTS native=true single=10 ranges=2 words=100 skipped=6 skipped_words=50 float_uploads=4 system_uploads=2 bool_uploads=1 fast_words=40 slow_words=60 fast_ns=80 slow_ns=360 fast_packets=2 slow_packets=3\n')
    totals = summarize_run(tmp_path)['shader_constant_bins']['true']
    assert totals['bins'] == 1 and totals['skipped_request_fraction'] == 0.5
    assert totals['fast_ns_per_word'] == 2 and totals['slow_ns_per_word'] == 6
    assert totals['float_uploads'] == 4


def test_black_frame_detection_ignores_alpha_and_rejects_truncated_data(tmp_path):
    header = bytearray(54)
    header[:2] = b'BM'
    struct.pack_into('<I', header, 10, 54)
    struct.pack_into('<IiiHHI', header, 14, 40, 2, -1, 1, 32, 0)
    path = tmp_path/'output.bmp'
    path.write_bytes(header+bytes([0,0,0,255,0,0,0,255]))
    assert inspect_native_readback(path)['all_black']
    path.write_bytes(header+bytes([0,0,0,255,0,0,1,0]))
    assert inspect_native_readback(path)['non_black_pixel_fraction'] == 0.5
    path.write_bytes(header+b'\x00')
    assert 'Truncated' in inspect_native_readback(path)['error']
