import csv
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from optimize_codegen import optimize_source, restore_source, dispatch, V3_MARKER, MARKER
from summarize_hot_functions import summarize


def test_ram_store_matches_byte_path_and_preserves_memory_watches(tmp_path):
    compiler=shutil.which('clang++')
    sdk=ROOT/'port/sdk-vulkan/include'
    generated=ROOT/'port/generated/default'
    if not compiler or not generated.is_dir():
        pytest.skip('Requires local compiler/SDK/generated PCH')
    executable=tmp_path/'ram.exe'
    compilation=subprocess.run([compiler,'-std=c++23','-O2','-msse4.1','-DNOMINMAX',
        '-DSPDLOG_FMT_EXTERNAL','-DSPDLOG_COMPILED_LIB','-I',str(ROOT/'port/src'),
        '-I',str(sdk),'-I',str(generated),str(ROOT/'tools/benchmark_ram_store.cpp'),
        '-o',str(executable)],capture_output=True,text=True)
    assert compilation.returncode==0,compilation.stderr
    result=subprocess.run([str(executable)],capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr
    assert 'validated_offsets,49152' in result.stdout
    assert 'write-watch-retry,mapped-RAM passed' in result.stdout
    assert 'alignment,trial,byte_ns,native_ns' in result.stdout


def test_previous_store_transform_upgrades_without_losing_original_body():
    generated=ROOT/'port/generated/default'
    candidate=next((p for p in generated.glob('*_recomp.*.cpp')
                    if 'sub_84723778_store_fast(' in p.read_text()),None)
    if not candidate:
        pytest.skip('Requires local generated routines')
    current=candidate.read_text()
    baseline=restore_source(current)
    old=current.replace(MARKER,V3_MARKER,1)
    for address,index in [('84723778',0),('84723CC0',1),('84724930',2)]:
        signature=f'DEFINE_REX_FUNC(sub_{address}) {{'
        if signature not in old: continue
        start=old.index(f'template<bool Count>\nstatic void sub_{address}_geometry_fast(')
        end=old.index('\n}\n',start)+4
        old=old[:start]+old[end:]
        start=old.index(f'static void sub_{address}_ram_fast(')
        end=old.index('\n}\n',start)+4
        old=old[:start]+old[end:]
        old=old.replace(dispatch(signature,address,index),dispatch(signature,address,index,3))
    assert restore_source(old)==baseline
    upgraded,count=optimize_source(old)
    assert count==16 and upgraded==current
    assert optimize_source(current)==(current,0)


def test_ram_summary_separates_variants_and_counts_fallbacks(tmp_path):
    path=tmp_path/'hot.csv'
    path.write_text('elapsed_ms,thread,function,optimized,unpack_optimized,store_optimized,ram_optimized,calls,work_units,wall_ns,wide_stores,byte_stores\n'
        '1000,1,0x84723778,1,1,1,0,10,100,4000,0,1600\n'
        '1000,1,0x84723778,1,1,1,1,10,100,2000,1500,100\n')
    result=summarize(path)['0x84723778']
    assert result['native_ram']['wide_stores']==1500
    assert result['native_ram']['byte_stores']==100
    assert result['native_ram']['ns_per_work_unit']==20
    assert result['pack_unpack_store']['ns_per_work_unit']==40


def test_guarded_store_fallback_keeps_preceding_native_paths_enabled(tmp_path):
    compiler=shutil.which('clang++');sdk=ROOT/'port/sdk/include'
    if not compiler or not sdk.is_dir():pytest.skip('Requires local compiler/SDK')
    source=tmp_path/'selector.cpp'
    source.write_text('''
#include "packed_vector_optimized.h"
void Ch2k8ConfigureHotFunctions(int,int,int,int,bool,const char*);
void Ch2k8ConfigureGeometryBatch(int);
int main() {
 Ch2k8ConfigureGeometryBatch(1);simde_mm_setcsr(0x1F80);
 for(unsigned i=0;i<3;++i) if(!Ch2k8SelectGeometryBatch(i)) return 10;
 simde_mm_setcsr(0x1F00);
 for(unsigned i=0;i<3;++i) if(Ch2k8SelectGeometryBatch(i)) return 11;
 simde_mm_setcsr(0x1F80);Ch2k8ConfigureGeometryBatch(0);
 for(unsigned i=0;i<3;++i) if(Ch2k8SelectGeometryBatch(i)) return 12;
 if(Ch2k8HotProfilingEnabled())return 13;
 Ch2k8ConfigureHotFunctions(1,1,1,1,false,nullptr);
 if(!Ch2k8SelectFastRamStore(0)||!Ch2k8SelectFastRamStore(1)||Ch2k8SelectFastRamStore(2)) return 1;
 Ch2k8ConfigureHotFunctions(1,1,1,1,true,nullptr);
 if(!Ch2k8SelectFastRamStore(2)) return 2;
 Ch2k8ConfigureHotFunctions(1,1,1,0,true,nullptr);
 for(unsigned i=0;i<3;++i) if(Ch2k8SelectFastRamStore(i)) return 3;
 Ch2k8ConfigureHotFunctions(1,1,1,2,false,nullptr);
 for(unsigned i=0;i<128;++i) if(Ch2k8SelectFastRamStore(2)) return 4;
}
''')
    executable=tmp_path/'selector.exe'
    result=subprocess.run([compiler,'-std=c++23','-O2','-msse4.1','-DNOMINMAX',
        '-DSPDLOG_FMT_EXTERNAL','-DSPDLOG_COMPILED_LIB','-I',str(ROOT/'port/src'),'-I',str(sdk),
        str(source),str(ROOT/'port/src/hot_functions.cpp'),'-o',str(executable)],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    result=subprocess.run([str(executable)],capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr
