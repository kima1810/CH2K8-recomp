"""Exercise the real PowerShell argument builder without opening a game or UI."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('backend,mode,flags', [
    ('d3d12', 'windowed', ['--no-fullscreen', '--render_target_path_d3d12=rtv', '--execute_unclipped_draw_vs_on_cpu', '--no-async_shader_compilation']),
    ('vulkan', 'exclusive', ['--fullscreen', '--fullscreen_exclusive', '--render_target_path_vulkan=fsi']),
    ('vulkan', 'borderless', ['--fullscreen', '--no-fullscreen_exclusive', '--render_target_path_vulkan=fsi']),
])
def test_launcher_builds_explicit_backend_and_display_args(tmp_path, backend, mode, flags):
    shell = shutil.which('powershell.exe')
    if not shell:
        pytest.skip('Requires Windows PowerShell')
    data = tmp_path / 'disc with spaces'
    data.mkdir()
    (data / 'default.xex').write_bytes(b'')
    executable = tmp_path / 'unused executable.exe'
    executable.write_bytes(b'')
    command = [shell, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
               str(ROOT/'tools/launch_ch2k8.ps1'), '-ValidateOnly',
               '-Renderer', backend, '-WindowMode', mode, '-Resolution', '1920x1080',
               '-RefreshRate', '120', '-GameData', str(data), '-Executable', str(executable)]
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    configuration = json.loads(result.stdout)
    arguments = configuration['arguments']
    assert f'--game_data_root={data}' in arguments
    assert f'--ch2k8_renderer={backend}' in arguments
    assert '--resolution=1920x1080' in arguments
    assert '--video_mode_refresh_rate=120' in arguments
    assert '--ch2k8_guest_refresh_rate=60' in arguments
    assert all(flag in arguments for flag in flags)
    if backend == 'vulkan':
        assert not any('render_target_path_d3d12' in arg for arg in arguments)
    # A missing disc must fail before launching or saving configuration.
    (data/'default.xex').unlink()
    failure = subprocess.run(command, capture_output=True, text=True)
    assert failure.returncode != 0
    assert 'default.xex' in failure.stderr


@pytest.mark.parametrize('backend,path,target', [
    ('d3d12', 'native', '--render_target_path_d3d12=rtv'),
    ('d3d12', 'accurate', '--render_target_path_d3d12=rov'),
    ('vulkan', 'native', '--render_target_path_vulkan=fbo'),
    ('vulkan', 'accurate', '--render_target_path_vulkan=fsi'),
])
def test_launcher_selects_native_or_accurate_targets(tmp_path, backend, path, target):
    shell = shutil.which('powershell.exe')
    if not shell:
        pytest.skip('Requires Windows PowerShell')
    data = tmp_path/'disc'
    data.mkdir()
    (data/'default.xex').write_bytes(b'')
    program = tmp_path/'game.exe'
    program.write_bytes(b'')
    result = subprocess.run([shell, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
        str(ROOT/'tools/launch_ch2k8.ps1'), '-ValidateOnly', '-Renderer', backend,
        '-RenderPath', path, '-Executable', str(program), '-GameData', str(data)],
        capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    arguments=json.loads(result.stdout)['arguments']
    assert target in arguments
    bounded='--execute_unclipped_draw_vs_on_cpu' in arguments
    synchronous='--no-async_shader_compilation' in arguments
    assert bounded == (backend=='d3d12' and path=='native')
    assert synchronous == bounded


def fake_pe(import_dll=None):
    import struct
    data = bytearray(1024)
    data[:2] = b'MZ'
    struct.pack_into('<I', data, 60, 0x80)
    data[0x80:0x84] = b'PE\0\0'
    struct.pack_into('<HH', data, 0x84, 0x8664, 1)
    struct.pack_into('<H', data, 0x94, 240)
    struct.pack_into('<H', data, 0x98, 0x20b)
    struct.pack_into('<IIII', data, 0x188+8, 512, 0x1000, 512, 512)
    if import_dll:
        struct.pack_into('<II', data, 0x98+112+8, 0x1000, 40)
        struct.pack_into('<I', data, 512+12, 0x1040)
        name = import_dll.encode('ascii')+b'\0'
        data[576:576+len(name)] = name
    return bytes(data)


@pytest.mark.skipif(not (ROOT/'port/out/build/win-amd64-vulkan/ch2k8_tools.exe').is_file(), reason='Build native asset tools first')
def test_portable_beta_package_is_self_contained(tmp_path):
    import hashlib
    import zipfile

    shell = shutil.which('powershell.exe')
    if not shell:
        pytest.skip('Requires Windows PowerShell')
    build = tmp_path / 'build'
    build.mkdir()
    for name in ('ch2k8.exe', 'rexruntime.dll', 'rexgpu-xenos.dll', 'ch2k8_tools.exe'):
        (build / name).write_bytes(fake_pe())
    output = tmp_path / 'beta output'
    result = subprocess.run([shell, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
        str(ROOT / 'tools/package_beta.ps1'), '-BuildDirectory', str(build),
        '-OutputDirectory', str(output)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    archive, = output.glob('*.zip')
    moved = tmp_path / 'installation with spaces'
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(moved)
    install, = moved.iterdir()
    data = tmp_path / 'my disc'
    data.mkdir()
    (data / 'default.xex').write_bytes(b'private game data')
    validation = subprocess.run([shell, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
        str(install / 'tools/launch_ch2k8.ps1'), '-ValidateOnly', '-GameData', str(data)],
        capture_output=True, text=True)
    assert validation.returncode == 0, validation.stderr
    config = json.loads(validation.stdout)
    assert Path(config['executable']) == install / 'ch2k8.exe'
    assert f'--user_data_root={install / "port/userdata"}' in config['arguments']
    for entry in (install / 'SHA256SUMS.txt').read_text().splitlines():
        digest, name = entry.split('  ', 1)
        assert hashlib.sha256((install / name).read_bytes()).hexdigest() == digest
    assert not list(install.rglob('*.xex'))
    assert not list(install.rglob('*.pdb'))
    assert (install / 'tools/verify_beta.ps1').is_file()
    assert not list(install.rglob('*.py'))
    assert not list(install.rglob('*python*'))
    assert (install / 'START HERE.md').is_file()


def test_relative_paths_follow_powershell_location(tmp_path):
    shell=shutil.which('powershell.exe')
    if not shell:pytest.skip('Requires Windows PowerShell')
    disc=tmp_path/'disc';disc.mkdir();(disc/'default.xex').write_bytes(b'fixture')
    (tmp_path/'game.exe').write_bytes(b'fixture')
    wrapper=tmp_path/'location.ps1'
    wrapper.write_text("""param($Directory,$Launcher)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $Directory
& $Launcher -ValidateOnly -GameData disc -Executable game.exe
""",encoding='utf-8')
    result=subprocess.run([shell,'-NoProfile','-ExecutionPolicy','Bypass','-File',str(wrapper),'-Directory',str(tmp_path),'-Launcher',str(ROOT/'tools/launch_ch2k8.ps1')],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    config=json.loads(result.stdout)
    assert Path(config['executable'])==tmp_path/'game.exe'
    assert f'--game_data_root={disc}' in config['arguments']
