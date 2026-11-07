import shutil
import subprocess
import sys
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from prepare_native_vertex_sdk import patch_vertex_fetch,prepare_native_vertex


def test_exact_vertex_endian_selector_and_shader_key(tmp_path):
    compiler=shutil.which('clang++')
    if not compiler:pytest.skip('Requires clang++')
    source=tmp_path/'vertex.cpp'
    source.write_text(r'''
#include "native_vertex_state.h"
#include <cassert>
int main() {
 using rex::graphics::ch2k8::SelectVertexEndian;
 uint32_t bitmap[3]{},values[96]{};
 assert(!SelectVertexEndian(bitmap,[&](auto i){return values[i];}));
 for(unsigned endian=0;endian<4;++endian)for(unsigned at=0;at<96;++at) {
  for(auto& v:bitmap)v=0;
  bitmap[at/32]=1u<<(at%32);values[at]=endian;
  assert(SelectVertexEndian(bitmap,[&](auto i){return values[i];})==endian+1);
  const unsigned other=(at+1)%96;bitmap[other/32]|=1u<<(other%32);
  values[other]=(endian+1)%4;
  assert(!SelectVertexEndian(bitmap,[&](auto i){return values[i];}));
  values[other]=endian;
  assert(SelectVertexEndian(bitmap,[&](auto i){return values[i];})==endian+1);
 }
}
''')
    exe=tmp_path/'vertex.exe'
    r=subprocess.run([compiler,'-std=c++20','-O2','-I',str(ROOT/'port/sdk_patches'),str(source),'-o',str(exe)],capture_output=True,text=True)
    assert r.returncode==0,r.stderr
    assert subprocess.run([str(exe)]).returncode==0


def test_vertex_patch_checks_pinned_input_and_is_idempotent(tmp_path):
    sdk=ROOT/'work/third_party/rexglue-vulkan'
    if not (sdk/'.git').exists():pytest.skip('Requires pinned SDK')
    relative='src/graphics/pipeline/shader/dxbc_translator_fetch.cpp'
    original=subprocess.check_output(['git','-C',str(sdk),'show','HEAD:'+relative],text=True)
    path=tmp_path/relative;path.parent.mkdir(parents=True);path.write_text(original)
    # The patch uses Git for provenance, so test source validation with a local
    # repository containing the exact pinned file.
    subprocess.run(['git','init','-q',str(tmp_path)],check=True)
    subprocess.run(['git','-C',str(tmp_path),'add','.'],check=True)
    subprocess.run(['git','-C',str(tmp_path),'-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','Pinned fixture'],check=True)
    prepare_native_vertex(tmp_path);expected=path.read_bytes()
    prepare_native_vertex(tmp_path);assert path.read_bytes()==expected
    assert patch_vertex_fetch(path.read_text())==path.read_text()
    path.write_text(path.read_text()+'\n// unknown edit\n')
    with pytest.raises(ValueError,match='Unreviewed'):prepare_native_vertex(tmp_path)


def test_constant_bookkeeping_exactness_and_local_timing(tmp_path):
    compiler=shutil.which('clang++')
    sdk=ROOT/'port/sdk-vulkan/include'
    if not compiler or not sdk.is_dir():pytest.skip('Requires compiler and SDK')
    exe=tmp_path/'constants.exe'
    r=subprocess.run([compiler,'-std=c++20','-O2','-msse4.1','-DNOMINMAX','-I',str(ROOT/'port/src'),
        '-I',str(sdk),str(ROOT/'tools/benchmark_render_constants.cpp'),'-o',str(exe)],capture_output=True,text=True)
    assert r.returncode==0,r.stderr
    r=subprocess.run([str(exe)],capture_output=True,text=True)
    assert r.returncode==0,r.stdout+r.stderr
    assert 'guarded packet tails passed' in r.stdout


def test_geometry_modification_key_has_no_collisions(tmp_path):
    compiler=shutil.which('clang++')
    sdk=ROOT/'port/sdk-vulkan/include'
    if not compiler or not sdk.is_dir():pytest.skip('Requires prepared SDK')
    source=tmp_path/'key.cpp'
    source.write_text(r'''
#include <rex/graphics/pipeline/shader/dxbc_translator.h>
#include <cassert>
using rex::graphics::DxbcShaderTranslator;
int main() {
 using M=DxbcShaderTranslator::Modification;
 static_assert(M::kVersion==0x20261109);
 for(uint32_t mask=0;mask<65536;++mask)for(uint32_t endian=0;endian<=4;++endian)
 for(uint32_t memory=0;memory<=2;++memory)for(uint32_t index=0;index<=4;++index) {
  M m;m.vertex.interpolator_mask=mask;m.vertex.output_point_size=1;
  const auto original=m.value;
  m.vertex.native_vertex_endian=endian;m.vertex.native_vertex_memory=memory;
  m.vertex.native_index_endian=index;
  assert(m.vertex.interpolator_mask==mask && m.vertex.output_point_size==1);
  assert(m.vertex.native_vertex_endian==endian && m.vertex.native_vertex_memory==memory && m.vertex.native_index_endian==index);
  assert(m.value==(original|(uint64_t(endian)<<36)|(uint64_t(memory)<<39)|(uint64_t(index)<<41)));
 }
}
''')
    exe=tmp_path/'key.exe'
    result=subprocess.run([compiler,'-std=c++23','-O2','-DNOMINMAX','-DSPDLOG_FMT_EXTERNAL',
        '-DSPDLOG_COMPILED_LIB','-I',str(sdk),str(source),'-o',str(exe)],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    assert subprocess.run([str(exe)]).returncode==0


@pytest.mark.parametrize('mode,flag',[('baseline','--no-ch2k8_native_vertex_fetch'),
    ('optimized','--ch2k8_native_vertex_fetch'),('compare','--ch2k8_native_vertex_fetch')])
def test_geometry_capture_arguments(tmp_path,mode,flag):
    import json
    shell=shutil.which('powershell.exe')
    if not shell:pytest.skip('Requires PowerShell')
    disc=tmp_path/'disc';disc.mkdir();(disc/'default.xex').touch()
    executable=tmp_path/'unused.exe';executable.touch()
    result=subprocess.run([shell,'-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'tools/capture_gpu_workload.ps1'),
        '-ValidateOnly','-Executable',str(executable),'-RenderDoc',str(executable),'-GameData',str(disc),
        '-VertexFetch',mode,'-DumpShaders'],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    arguments=json.loads(result.stdout)['arguments']
    assert flag in arguments
    assert ('--ch2k8_vertex_fetch_compare' in arguments)==(mode=='compare')
    assert '--d3d12_dxbc_disasm' in arguments and '--no-store_shaders' in arguments


def test_draw_key_retains_memexport_and_disabled_paths(tmp_path):
    compiler=shutil.which('clang++')
    sdk=ROOT/'port/sdk-vulkan/include'
    upstream=ROOT/'work/third_party/rexglue-vulkan/src/graphics/d3d12/command_processor.cpp'
    if not compiler or not upstream.is_file():pytest.skip('Requires pinned source/SDK')
    text=upstream.read_text()
    begin=text.index('  if(vertex_shader_modification.vertex.native_vertex_memory) {')
    end=text.index('  DxbcShaderTranslator::Modification pixel_shader_modification',begin)
    block=text[begin:end]
    source=tmp_path/'draw.cpp'
    source.write_text('''#include <rex/graphics/pipeline/shader/dxbc_translator.h>
#include <cassert>
using rex::graphics::DxbcShaderTranslator;
namespace xenos=rex::graphics::xenos;
using M=DxbcShaderTranslator::Modification;
void apply(M& vertex_shader_modification,bool memexport_used,unsigned index) {
 struct {xenos::Endian host_shader_index_endian;} primitive_processing_result{xenos::Endian(index)};
'''+block+r'''}
int main() {
 for(unsigned index=0;index<4;++index)for(unsigned endian=0;endian<=4;++endian)for(bool gpu:{false,true}) {
  M baseline;baseline.vertex.interpolator_mask=123;const auto original=baseline.value;
  apply(baseline,gpu,index);assert(baseline.value==original);
  M native;native.vertex.interpolator_mask=123;native.vertex.native_vertex_endian=endian;
  native.vertex.native_vertex_memory=1;apply(native,gpu,index);
  assert(native.vertex.interpolator_mask==123);
  if(gpu)assert(native.value==original);
  else {
    assert(native.vertex.native_vertex_endian==endian);
    assert(native.vertex.native_vertex_memory==1 && native.vertex.native_index_endian==index+1);
  }
 }
}
''')
    exe=tmp_path/'draw.exe'
    result=subprocess.run([compiler,'-std=c++23','-O2','-DNOMINMAX','-DSPDLOG_FMT_EXTERNAL',
        '-DSPDLOG_COMPILED_LIB','-I',str(sdk),str(source),'-o',str(exe)],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    assert subprocess.run([str(exe)]).returncode==0
