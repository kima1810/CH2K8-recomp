"""Source-patch safety for optional native wait attribution."""
import subprocess
from pathlib import Path
import pytest
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from prepare_native_gpu_sdk import patch_common, patch_backend, prepare_native_gpu
from prepare_native_sync_sdk import patch_sync, prepare_sync
ROOT=Path(__file__).resolve().parents[1]

def test_sync_upgrade_idempotence_and_atomic_refusal(tmp_path, monkeypatch):
    sdk=ROOT/'work/third_party/rexglue-vulkan'
    if not sdk.exists():pytest.skip('Requires pinned SDK')
    originals={}
    for relative,kind in [('src/graphics/command_processor.cpp','common'),('src/graphics/d3d12/command_processor.cpp','d3d12'),('src/graphics/vulkan/command_processor.cpp','vulkan')]:
        text=subprocess.check_output(['git','-C',str(sdk),'show','HEAD:'+relative],text=True)
        originals[relative]=text
        previous=patch_common(text) if kind=='common' else patch_backend(text,kind)
        path=tmp_path/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(previous)
    monkeypatch.setattr(subprocess,'check_output',lambda args,**kw:originals[args[-1].removeprefix('HEAD:')])
    prepare_sync(tmp_path)
    before={p:p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    prepare_native_gpu(tmp_path);prepare_sync(tmp_path)
    assert all(p.read_bytes()==data for p,data in before.items())
    changed=tmp_path/'src/graphics/d3d12/command_processor.cpp'
    changed.write_text(changed.read_text()+'\n// unknown external edit\n')
    before={p:p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    with pytest.raises(ValueError,match='Unreviewed synchronization'):
        prepare_sync(tmp_path)
    assert all(p.read_bytes()==data for p,data in before.items())
