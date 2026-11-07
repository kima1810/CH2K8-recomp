import json
import shutil
import subprocess
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from prepare_native_shader_sdk import patch_header, patch_pipeline, patch_output, patch_shader, prepare_native_shaders, patch_header_v3, patch_pipeline_v3, patch_output_v3
from summarize_shader_comparison import summarize


def test_exact_state_keys_and_fold_masks(tmp_path):
    compiler = shutil.which('clang++')
    if not compiler:
        pytest.skip('Requires C++ compiler')
    source = tmp_path/'state.cpp'
    source.write_text(r'''
#include "native_pixel_state.h"
#include <set>
#include <cstdio>
using namespace rex::graphics::ch2k8;
int main() {
 std::set<unsigned> keys,full_keys;
 unsigned checks=0;
 for(unsigned samples=0;samples<3;++samples) for(unsigned flags=0;flags<16;++flags) {
  auto state=PackPixelState(samples,flags<<6);
  if(state>=65536 || !keys.insert(state).second || !PixelStateEnabled(state)) return 1;
  if(PixelFlags(state)!=(flags<<6)) return 2;
  if(SampleLog2(state,0)!=unsigned(samples>=2) || SampleLog2(state,1)!=unsigned(samples>=1)) return 3;
  for(unsigned mask=0;mask<16;++mask) {
   if(!CanFoldFlags(state,mask<<6) || (PixelFlags(state)&(mask<<6)) != ((flags<<6)&(mask<<6))) return 4;
   if(CanFoldFlags(state,(mask<<6)|(1<<14)) || CanFoldFlags(0,mask<<6)) return 5;
   ++checks;
  }
  for(unsigned swizzle=0;swizzle<256;++swizzle)
   if(CanFoldSamples(state,swizzle) != ((swizzle&0xAA)==0)) return 6;
  for(unsigned format=0;format<16;++format) for(unsigned index=0;index<32;++index) {
   unsigned blend=0xFFFFFFFFu;
   if(index) blend=kBlendControls[index-1];
   auto full=PackPixelState(samples,flags<<6,format,blend);
   if(ColorFormat(full)!=format || HasBlend(full)!=bool(index) ||
      (index && BlendControl(full)!=blend) ||
      PixelFlags(full)!=(flags<<6) || !PixelStateEnabled(full)) return 7;
   if(!full_keys.insert(full).second || FullWrite(full)) return 8;
   auto full_write=PackPixelState(samples,flags<<6,format,blend,true);
   if(!FullWrite(full_write) || !full_keys.insert(full_write).second ||
      PixelFlags(full_write)!=PixelFlags(full) || ColorFormat(full_write)!=ColorFormat(full) ||
      BlendControl(full_write)!=BlendControl(full) || SampleLog2(full_write,0)!=SampleLog2(full,0)) return 16;
  }
 }
 if(full_keys.size()!=49152) return 9;
 if(PackPixelState(3,0)!=0 || PixelStateEnabled(0) || FullWrite(0x8000)) return 17;
 unsigned interpolation_checks=0;
 for(unsigned mask=0;mask<65536;++mask) for(unsigned pattern=0;pattern<8;++pattern) {
  const unsigned choices[]={0u,65535u,0xAAAAu,0x5555u,0xFF00u,0x00FFu,mask*1664525u,mask*1013904223u};
  auto centroid=choices[pattern]&mask&65535u;
  auto packed=PackInterpolators(mask,centroid);
  if(packed>43046720u || InterpolatorMask(packed)!=mask ||
     InterpolatorMask(packed,true)!=centroid) return 10;
  for(unsigned raw=0;raw<128;++raw) {
   auto depth=PackDepthState(raw<<14);
   const bool encoded=raw==0 || ((raw&1u) && (raw>>1)<62u);
   if(depth>=64 || bool(depth)!=encoded || (depth && DepthFlags(depth)!=(raw<<14))) return 11;
   auto combined=packed|(depth<<26);
   if((combined&0x3FFFFFFu)!=packed || (combined>>26)!=depth) return 12;
  }
  ++interpolation_checks;
 }
 if(!CanFoldFlags(PackPixelState(2,0),1u<<20,PackDepthState(0))) return 13;
 if(!CanFoldFlags(PackPixelState(2,0),63u<<14,PackDepthState(0))) return 14;
 if(CanFoldFlags(PackPixelState(2,0),63u<<14,0)) return 15;
 printf("%u exact state/mask comparisons; 49152 unique full keys\n",checks);
 printf("%u interpolation round-trips with 128 depth combinations\n",interpolation_checks);
}
''')
    exe = tmp_path/'state.exe'
    build = subprocess.run([compiler,'-std=c++17','-O2','-I',str(ROOT/'port/sdk_patches'),str(source),'-o',str(exe)],capture_output=True,text=True)
    assert build.returncode == 0, build.stderr
    result = subprocess.run([str(exe)],capture_output=True,text=True)
    assert result.returncode == 0, result.stdout+result.stderr
    assert '768 exact state/mask comparisons' in result.stdout
    assert '524288 interpolation round-trips' in result.stdout


def test_pinned_shader_patches_and_atomic_rejection(tmp_path, monkeypatch):
    upstream = ROOT/'work/third_party/rexglue-vulkan'
    if not upstream.is_dir():
        pytest.skip('Requires local pinned SDK')
    functions = {
        'include/rex/graphics/pipeline/shader/dxbc_translator.h': patch_header,
        'src/graphics/d3d12/pipeline_cache.cpp': patch_pipeline,
        'src/graphics/pipeline/shader/dxbc_translator_om.cpp': patch_output,
        'src/graphics/pipeline/shader/dxbc_translator.cpp': patch_shader,
    }
    originals = {}
    for name, patch in functions.items():
        original = subprocess.check_output(['git','-C',str(upstream),'show','HEAD:'+name],text=True)
        originals[name] = original
        path = tmp_path/name
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(original)
        assert patch(original) != original
    monkeypatch.setattr(subprocess,'check_output',lambda args,**kw: originals[args[-1].removeprefix('HEAD:')])
    # Upgrade the exact previously published three-file shader patch atomically.
    previous = dict(zip(functions, (patch_header_v3, patch_pipeline_v3, patch_output_v3, lambda text:text)))
    for name, patch in previous.items():
        (tmp_path/name).write_text(patch(originals[name]))
    prepare_native_shaders(tmp_path)
    before = {name:(tmp_path/name).read_bytes() for name in functions}
    prepare_native_shaders(tmp_path)
    assert all((tmp_path/name).read_bytes()==value for name,value in before.items())
    changed = tmp_path/'src/graphics/pipeline/shader/dxbc_translator_om.cpp'
    changed.write_text(changed.read_text()+'\n// unrelated local modification\n')
    before = {p:p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    with pytest.raises(ValueError,match='Unreviewed shader'):
        prepare_native_shaders(tmp_path)
    assert all(p.read_bytes()==value for p,value in before.items())


@pytest.mark.parametrize('state,flag',[('baseline','--no-ch2k8_native_pixel_state'),('optimized','--ch2k8_native_pixel_state')])
def test_bounded_capture_configuration(tmp_path,state,flag):
    shell=shutil.which('powershell.exe')
    if not shell:pytest.skip('Requires PowerShell')
    disc=tmp_path/'disc with spaces';disc.mkdir();(disc/'default.xex').touch()
    exe=tmp_path/'unused exe.exe';exe.touch()
    command=[shell,'-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'tools/capture_gpu_workload.ps1'),'-ValidateOnly',
             '-Executable',str(exe),'-RenderDoc',str(exe),'-GameData',str(disc),'-ShaderState',state]
    result=subprocess.run(command,capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    config=json.loads(result.stdout)
    assert flag in config['arguments'] and '--render_target_path_d3d12=rov' in config['arguments']
    assert config['duration_seconds']==200 and not config['matched_scene']
    assert not Path(config['run_root']).exists()
    bad=subprocess.run(command+['-DurationSeconds','130'],capture_output=True,text=True)
    assert bad.returncode != 0 and 'exceed capture delay' in bad.stderr


def test_paired_counter_summary_requires_matching_warmed_trials(tmp_path):
    path=tmp_path/'paired.tsv'
    rows=['trial\tvariant\tevent\tms']
    for trial in (1,2,3):
        for name,values in [('original',(3,7)),('specialized',(2,6))]:
            for event,value in zip((10,20),values):
                rows.append(f'{trial}\t{name}\t{event}\t{value}')
    path.write_text('\n'.join(rows)+'\n')
    result=summarize(path,10)
    assert result['median_sum_reduction']==pytest.approx(.2)
    assert result['median_target_reduction']==pytest.approx(1/3)
    assert 'not displayed FPS' in result['limits']
    path.write_text('\n'.join(rows[:-1])+'\n')
    with pytest.raises(ValueError,match='Mismatched'):
        summarize(path,10)


def test_full_write_contract_against_original_format_masks(tmp_path):
    compiler=shutil.which('clang++')
    sdk=ROOT/'work/third_party/rexglue-vulkan'
    if not compiler or not sdk.exists():pytest.skip('Requires compiler and pinned SDK')
    # Execute the actual upstream format-mask implementation, not a mirrored model.
    text=(sdk/'include/rex/graphics/xenos.h').read_text()
    start=text.index('enum class ColorRenderTargetFormat :')
    enum=text[start:text.index('};',start)+2]
    text=(sdk/'src/graphics/pipeline/render_target/cache.cpp').read_text()
    start=text.index('void RenderTargetCache::GetPSIColorFormatInfo(')
    function=text[start:text.index('\n}\n',start)+3].replace('RenderTargetCache::GetPSIColorFormatInfo','OriginalKeepMask')
    source=tmp_path/'contract.cpp'
    source.write_text('#include <cmath>\n#include <cstdint>\n#include "native_pixel_state.h"\n#define assert_unhandled_case(...) ((void)0)\nnamespace xenos {\n'+enum+'\n}\n'+function+r'''
int main() {
  using namespace rex::graphics::ch2k8;
  for(unsigned format=0;format<16;++format) for(unsigned mask=0;mask<256;++mask) {
    float clamps[4];unsigned low,high;
    OriginalKeepMask(xenos::ColorRenderTargetFormat(format),mask&15,
        clamps[0],clamps[1],clamps[2],clamps[3],low,high);
    if(FullWriteEligible(format,mask) && (low || high)) return 1;
    if((format==8 || format==9 || format==11 || format==13) && FullWriteEligible(format,mask)) return 2;
  }
}
''')
    exe=tmp_path/'contract.exe'
    result=subprocess.run([compiler,'-std=c++17','-O2','-I',str(ROOT/'port/sdk_patches'),str(source),'-o',str(exe)],text=True,capture_output=True)
    assert result.returncode==0,result.stderr
    assert subprocess.run([str(exe)]).returncode==0
