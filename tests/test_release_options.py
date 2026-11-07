import json
import shutil
import subprocess
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('configuration,optimization',[('Release','-O2'),('RelWithDebInfo','-O2'),('MinSizeRel','-Os'),('Debug',None)])
def test_release_targets_are_optimized_with_empty_global_flags(tmp_path,configuration,optimization):
    cmake=shutil.which('cmake');compiler=shutil.which('clang++')
    if not cmake or not compiler:pytest.skip('Requires CMake and clang++')
    (tmp_path/'main.cpp').write_text('''#include <cstdint>
#include <limits>
__attribute__((noinline)) bool increasing(int64_t x){return x+1>x;}
int main(){volatile int64_t x=std::numeric_limits<int64_t>::max();return increasing(x)?1:0;}
''')
    module=(ROOT/'port/cmake/Ch2k8BuildOptions.cmake').as_posix()
    (tmp_path/'CMakeLists.txt').write_text(f'''cmake_minimum_required(VERSION 3.25)
project(ReleaseOptions LANGUAGES CXX)
include("{module}")
add_executable(host main.cpp)
add_library(guest OBJECT main.cpp)
ch2k8_apply_build_options(host)
ch2k8_apply_build_options(guest)
''')
    result=subprocess.run([cmake,'-S',str(tmp_path),'-B',str(tmp_path/'build'),'-G','Ninja',
        '-DCMAKE_CXX_COMPILER='+compiler,'-DCMAKE_BUILD_TYPE='+configuration,
        '-DCMAKE_CXX_FLAGS_'+configuration.upper()+'=','-DCMAKE_EXPORT_COMPILE_COMMANDS=ON'],capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr
    commands=json.loads((tmp_path/'build/compile_commands.json').read_text())
    assert len(commands)==2
    for command in commands:
        args=command['command']
        assert '-fwrapv' in args
        assert '-ffp-model=strict' in args and '-fno-strict-aliasing' in args
        if optimization:
            assert optimization in args and 'NDEBUG' in args
        else:
            assert '-O2' not in args and '-Os' not in args and 'NDEBUG' not in args
    built=subprocess.run([cmake,'--build',str(tmp_path/'build')],capture_output=True,text=True)
    assert built.returncode==0,built.stdout+built.stderr
    executable=tmp_path/'build'/'host.exe'
    if not executable.exists():executable=tmp_path/'build'/'host'
    assert subprocess.run([str(executable)]).returncode==0


def test_actual_release_build_rules_optimize_generated_and_host_code():
    build=ROOT/'port/out/build/win-amd64-vulkan'
    if not (build/'build.ninja').is_file():pytest.skip('Requires configured native game build')
    if 'CMAKE_BUILD_TYPE:STRING=Release' not in (build/'CMakeCache.txt').read_text():
        pytest.skip('Requires Release configuration')
    text=(build/'build.ninja').read_text()
    for marker in ('generated/default/ch2k8_recomp.0.cpp.obj:', 'src/main.cpp.obj:', 'asset_codec.cpp.obj:'):
        start=text.index(marker);end=text.index('\n\n',start)
        rule=text[start:end]
        assert '-fwrapv' in rule,rule
        assert '-O2' in rule and '-DNDEBUG' in rule,rule
        assert '-ffp-model=strict' in rule and '-fno-strict-aliasing' in rule,rule


@pytest.mark.parametrize('program,marker',[
    ('benchmark_vector_pack.cpp','validated_vectors,'),
    ('benchmark_vector_unpack.cpp','validated_vectors,'),
    ('benchmark_ram_store.cpp','write-watch-retry,mapped-RAM passed')])
def test_release_policy_preserves_geometry_numeric_and_memory_contracts(tmp_path,program,marker):
    compiler=shutil.which('clang++');sdk=ROOT/'port/sdk-vulkan/include'
    generated=ROOT/'port/generated/default'
    if not compiler or not sdk.exists() or not generated.exists():pytest.skip('Requires native SDK/generated code')
    executable=tmp_path/'geometry.exe'
    result=subprocess.run([compiler,'-std=c++23','-O2','-DNDEBUG','-fwrapv','-fno-strict-aliasing','-ffp-model=strict',
        '-msse4.1','-DNOMINMAX','-DSPDLOG_FMT_EXTERNAL','-DSPDLOG_COMPILED_LIB',
        '-I',str(ROOT/'port/src'),'-I',str(sdk),'-I',str(generated),str(ROOT/'tools'/program),'-o',str(executable)],
        capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    result=subprocess.run([str(executable)],capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr
    assert marker in result.stdout
