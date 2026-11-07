import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from optimize_codegen import optimize_source, restore_source, scalar_pack, scalar_unpack, dispatch, MARKER, OLD_MARKER
from summarize_instruction_samples import summarize, pdb_checksums
from summarize_hot_functions import summarize as hot_summary


def test_unpack_matches_scalar_boundaries_random_bits_aliases_and_scratch(tmp_path):
    compiler = shutil.which('clang++')
    sdk = ROOT/'port/sdk/include'
    if not compiler or not sdk.exists():
        pytest.skip('Requires clang++ and local SDK')
    executable = tmp_path/'benchmark.exe'
    compilation = subprocess.run([compiler, '-std=c++23', '-O3', '-msse4.1',
        '-DNOMINMAX', '-DSPDLOG_FMT_EXTERNAL', '-DSPDLOG_COMPILED_LIB',
        '-I', str(ROOT/'port/src'), '-I', str(sdk),
        str(ROOT/'tools/benchmark_vector_unpack.cpp'), '-o', str(executable)], capture_output=True, text=True)
    assert compilation.returncode == 0, compilation.stderr
    result = subprocess.run([str(executable)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'validated_vectors,1003456' in result.stdout


def test_source_attribution_requires_matching_pdb_checksum(tmp_path):
    source = tmp_path/'test_recomp.0.cpp'
    source.write_bytes(b'\t// stvlx v0,r3,r4\n\tstore();\n')
    checksum = hashlib.md5(source.read_bytes()).hexdigest()
    checksums = pdb_checksums(f'- (MD5: {checksum.upper()}) {source}\n')
    symbols = [{'Symbol': [{'FunctionName': 'sub_84723778_fast', 'FileName': str(source), 'Line': 2}]}]
    result = summarize([{'thread':'1'}], symbols, checksums)
    assert result['guest_source_operation_samples'] == {'stvlx': 1}
    assert result['guest_function_samples'] == {'sub_84723778_fast': 1}
    source.write_bytes(source.read_bytes()+b'// changed\n')
    with pytest.raises(ValueError, match='does not match PDB'):
        summarize([{'thread':'1'}], symbols, checksums)


def test_old_pack_only_transform_upgrades_without_changing_retained_baseline():
    signature = 'DEFINE_REX_FUNC(sub_84723778) {'
    body = signature+'\n\tREX_FUNC_PROLOGUE();\n'+'\n'.join(
        scalar_pack(f'v{i}', 'v0', i%2) for i in range(16))+'\n'+scalar_unpack('v22','v23')+'\n}\n'
    current, _ = optimize_source(body)
    start = current.index('static void sub_84723778_unpack_fast(')
    end = current.index('\n}\n', start)+4
    old = current[:start]+current[end:]
    start = old.index('template<bool Count>\nstatic void sub_84723778_geometry_fast(')
    end = old.index('\n}\n', start)+4
    old = old[:start]+old[end:]
    start = old.index('static void sub_84723778_ram_fast(')
    end = old.index('\n}\n', start)+4
    old = old[:start]+old[end:]
    start = old.index('static void sub_84723778_store_fast(')
    end = old.index('\n}\n', start)+4
    old = old[:start]+old[end:]
    old = old.replace('#include "vector_store_optimized.h"\n', '')
    old = old.replace(MARKER+'\n', OLD_MARKER+'\n', 1).replace(
        dispatch(signature, '84723778', 0), dispatch(signature, '84723778', 0, 1))
    assert restore_source(old) == body
    upgraded, count = optimize_source(old)
    assert count == 16 and upgraded == current
    assert optimize_source(upgraded) == (upgraded, 0)


def test_hot_summary_keeps_pack_only_and_pack_unpack_separate(tmp_path):
    path = tmp_path/'hot.csv'
    path.write_text('elapsed_ms,thread,function,optimized,unpack_optimized,calls,work_units,wall_ns\n'
                    '1000,1,0x84723778,1,0,10,100,4000\n'
                    '1000,1,0x84723778,1,1,10,100,2500\n')
    result = hot_summary(path)['0x84723778']
    assert result['optimized']['ns_per_work_unit'] == 40
    assert result['pack_unpack']['ns_per_work_unit'] == 25
