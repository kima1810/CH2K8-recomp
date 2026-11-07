import shutil
import subprocess
import sys
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from geometry_batch_codegen import batch_normalization
from geometry_input_codegen import adapt_input_stream
from optimize_codegen import optimize_source, restore_source


def dot(dst,src):
    return f'\t// vmsum3fp128 v{dst},v{src},v{src}\n\tsimde_mm_store_ps(ctx.v{dst}.f32, simde_mm_dp_ps(simde_mm_load_ps(ctx.v{src}.f32), simde_mm_load_ps(ctx.v{src}.f32), 0xEF));\n'


def rsqrt(dst,src):
    return f'\t// vrsqrtefp128 v{dst},v{src}\n\tsimde_mm_store_ps(ctx.v{dst}.f32, simde_mm_div_ps(simde_mm_set1_ps(1), simde_mm_sqrt_ps(simde_mm_load_ps(ctx.v{src}.f32))));\n'


def test_scheduler_proves_broadcast_inputs_and_retains_disabled_positions():
    original=''.join(dot(i,i+10) for i in range(4))+''.join(rsqrt(i+4,i) for i in range(4))
    changed,count=batch_normalization(original)
    assert count==1 and changed.count('Ch2k8ReciprocalSqrt4(')==1
    assert changed.count('if (!native_batch)')==4
    assert all(rsqrt(i+4,i).split('\n')[1] in changed for i in range(4))
    for invalid in [original.replace('0xEF','0xE1'),
                    original.replace(rsqrt(4,0),rsqrt(4,19)),
                    original.replace(rsqrt(4,0),'loc_12345678:\n'+rsqrt(4,0)),
                    original.replace(rsqrt(4,0),'\t// bl 0x12345678\n\thelper(ctx, base);\n'+rsqrt(4,0))]:
        assert "Ch2k8ReciprocalSqrt4(" not in batch_normalization(invalid)[0]
    # A producer register overwritten before its original use is not a broadcast.
    overwritten=original.replace(rsqrt(4,0),'\t// vsubfp v0,v10,v11\n\tctx.v0 = unknown;\n'+rsqrt(4,0))
    assert "Ch2k8ReciprocalSqrt4(" not in batch_normalization(overwritten)[0]
    with pytest.raises(ValueError,match='Unrecognized'):
        batch_normalization(original.replace('set1_ps(1)','set1_ps(2)'))


def test_batch_retains_bits_aliases_and_fp_flags_in_all_host_modes(tmp_path):
    compiler=shutil.which('clang++');sdk=ROOT/'port/sdk-vulkan/include'
    if not compiler or not sdk.exists():pytest.skip('Requires native SDK and Clang')
    executable=tmp_path/'batch.exe'
    built=subprocess.run([compiler,'-std=c++23','-O2','-DNDEBUG','-fwrapv',
        '-fno-strict-aliasing','-ffp-model=strict','-msse4.1','-DNOMINMAX',
        '-DSPDLOG_FMT_EXTERNAL','-DSPDLOG_COMPILED_LIB','-I',str(ROOT/'port/src'),
        '-I',str(sdk),str(ROOT/'tools/benchmark_geometry_batch.cpp'),'-o',str(executable)],capture_output=True,text=True)
    assert built.returncode==0,built.stderr
    checked=subprocess.run([str(executable)],capture_output=True,text=True,timeout=45)
    assert checked.returncode==0,checked.stdout+checked.stderr
    assert 'validated_batches,800000' in checked.stdout


def test_local_input_loop_rejects_changed_stride_trip_count_and_control():
    generated=ROOT/'port/generated/default'
    candidate=next((p for p in generated.glob('*_recomp.*.cpp')
                    if 'DEFINE_REX_FUNC(sub_84723778)' in p.read_text()),None)
    if not candidate:pytest.skip('Requires local generated game code')
    original=restore_source(candidate.read_text())
    start=original.index('DEFINE_REX_FUNC(sub_84723778) {')
    body=original[start:original.index('\n}\n',start)+3]
    adapted,sites=adapt_input_stream(body,body,'84723778')
    assert sites>0 and adapted.count('input_span.Prepare(')==1
    assert 'volatile uint32_t*' in adapted
    for changed in [body.replace('ctx.r10.s64 + 48','ctx.r10.s64 + 52'),
                    body.replace('ctx.r5.s64 + -1','ctx.r5.s64 + -2'),
                    body.replace('if (ctx.cr6.gt) goto','if (!ctx.cr6.lt) goto')]:
        with pytest.raises(ValueError):adapt_input_stream(changed,changed,'84723778')
    # The complete body pin prevents unreviewed instructions elsewhere from
    # invalidating the newer alias and scheduling proofs.
    changed=original[:start]+body.replace('ctx.r10.s64 + 48','ctx.r10.s64 + 52',1)+original[start+len(body):]
    with pytest.raises(ValueError,match='re-audit required'):
        optimize_source(changed)
