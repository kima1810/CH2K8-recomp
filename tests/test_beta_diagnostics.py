"""Check useful reports for broken installations without launching the game."""
import json
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_failed_preflight_still_exports_redacted_report(tmp_path):
    shell = shutil.which('powershell.exe')
    if not shell: pytest.skip('Requires Windows PowerShell')
    # No game data or runtime binaries: exporting a failure must still work.
    report = tmp_path/'tester report.zip'
    result = subprocess.run([shell, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
        str(ROOT/'tools/launch_ch2k8.ps1'), '-GameData', str(tmp_path/'missing disc'),
        '-Executable', str(tmp_path/'missing.exe'), '-ReportOutput', str(report)],
        capture_output=True, text=True, timeout=45)
    assert result.returncode == 1, result.stdout+result.stderr
    assert report.is_file()
    with zipfile.ZipFile(report) as archive:
        names = archive.namelist()
        assert all(not name.endswith(('.xex','.dat','.exe','.dll')) for name in names)
        data = archive.read(next(name for name in names if name.endswith('report.json'))).decode('utf-8-sig')
    content = json.loads(data)
    assert not content['setup']['ready']
    assert any('executable missing' in failure for failure in content['setup']['failures'])
    assert str(tmp_path/'missing disc') not in data
    assert str(ROOT) not in data
    # The user's existing report is never silently replaced.
    original = report.read_bytes()
    repeated = subprocess.run([shell, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
        str(ROOT/'tools/launch_ch2k8.ps1'), '-GameData', str(tmp_path/'missing disc'),
        '-Executable', str(tmp_path/'missing.exe'), '-ReportOutput', str(report)],
        capture_output=True, text=True, timeout=45)
    assert repeated.returncode != 0
    assert report.read_bytes() == original


def test_setup_reports_missing_runtime_in_json(tmp_path):
    shell = shutil.which('powershell.exe')
    if not shell: pytest.skip('Requires Windows PowerShell')
    result = subprocess.run([shell, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
        str(ROOT/'tools/launch_ch2k8.ps1'), '-GameData', str(tmp_path/'missing'),
        '-Executable', str(tmp_path/'missing.exe'), '-CheckSetup'],
        capture_output=True, text=True, timeout=30)
    assert result.returncode == 1
    assert not json.loads(result.stdout)['ready']
