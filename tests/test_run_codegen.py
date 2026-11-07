import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import run_codegen


@pytest.mark.parametrize("changed,returncode", [(False, 0), (True, 0), (False, 1)])
def test_manifest_timestamp_is_preserved_only_for_successful_noop(tmp_path, monkeypatch, changed, returncode):
    manifest = tmp_path / "project.toml"
    manifest.write_text('[project]\nsdk_version = "0.10.0"\n')
    before = 1_700_000_000_000_000_000
    after = before + 10_000_000_000
    os.utime(manifest, ns=(before, before))

    def fake_codegen(command, check):
        assert command == ["rexglue.exe", "codegen", str(manifest)]
        assert check is False
        content = manifest.read_text()
        manifest.write_text(content.replace("0.10.0", "0.11.0") if changed else content)
        os.utime(manifest, ns=(after, after))
        return SimpleNamespace(returncode=returncode)

    monkeypatch.setattr(run_codegen.subprocess, "run", fake_codegen)
    assert run_codegen.run_codegen(Path("rexglue.exe"), manifest) == returncode
    assert manifest.stat().st_mtime_ns == (before if not changed and returncode == 0 else after)
    assert ('"0.11.0"' in manifest.read_text()) is changed


@pytest.mark.parametrize("body_changed", [False, True])
def test_sdk_rewrite_is_corrected_before_comparing_final_output(tmp_path, monkeypatch, body_changed):
    manifest = tmp_path / "project.toml"
    manifest.write_text('[project]\nname = "test"\n')
    generated = tmp_path / "generated"
    generated.mkdir()
    source = generated / "test_recomp.0.cpp"
    correct = "temp.s32 = (int64_t(vTemp.u64[0] << 44) >> 44);\n"
    source.write_text(correct)
    before = 1_700_000_000_000_000_000
    os.utime(source, ns=(before, before))

    def fake_codegen(command, check):
        source.write_text(correct.replace("int64_t", "int32_t") + ("// new body\n" if body_changed else ""))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(run_codegen.subprocess, "run", fake_codegen)
    assert run_codegen.run_codegen(Path("rexglue.exe"), manifest, generated) == 0
    assert "int32_t" not in source.read_text()
    assert (source.stat().st_mtime_ns != before) is body_changed
    assert ("// new body" in source.read_text()) is body_changed
