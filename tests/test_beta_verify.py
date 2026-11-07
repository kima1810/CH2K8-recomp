import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from verify_beta import verify, pe_imports
from test_launcher import fake_pe


def inventory(root):
    (root/'SHA256SUMS.txt').write_text(''.join(
        hashlib.sha256(path.read_bytes()).hexdigest()+'  '+path.relative_to(root).as_posix()+'\n'
        for path in sorted(root.rglob('*')) if path.is_file() and path.name!='SHA256SUMS.txt'),encoding='ascii')


def test_verifier_detects_missing_transitive_dll_and_tampering(tmp_path):
    for name in ('ch2k8.exe', 'rexruntime.dll', 'rexgpu-xenos.dll', 'ch2k8_tools.exe',
                 'tools/launch_ch2k8.ps1', 'tools/verify_beta.ps1', 'tools/beta_diagnostics.ps1', 'gamecontrollerdb.txt'):
        path = tmp_path/name
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(fake_pe())
    (tmp_path/'rexruntime.dll').write_bytes(fake_pe('MSVCP140.dll'))
    inventory(tmp_path)
    with pytest.raises(ValueError,match='Unbundled dependency'):
        verify(tmp_path)
    (tmp_path/'MSVCP140.dll').write_bytes(fake_pe('KERNEL32.dll'))
    inventory(tmp_path)
    assert verify(tmp_path)['verified']
    assert pe_imports(tmp_path/'rexruntime.dll')==['msvcp140.dll']
    (tmp_path/'ch2k8.exe').write_bytes(b'tampered')
    with pytest.raises(ValueError,match='Checksum mismatch'):
        verify(tmp_path)
